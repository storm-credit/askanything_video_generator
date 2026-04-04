"""자동 배포 스케줄러 — Day 파일 → 영상 생성 → 예약 업로드 파이프라인.

흐름:
  1. Day 파일 파싱 → 채널별 주제 추출
  2. 채널별 업로드 시간 자동 계산 (time_planner)
  3. 주제별 cutter.py → 이미지 → TTS → 렌더링
  4. YouTube 예약 업로드 (publishAt)

사용법:
  # API 엔드포인트
  POST /api/scheduler/run          → 오늘 Day 파일 자동 배포
  POST /api/scheduler/run?date=2026-04-05  → 특정 날짜
  GET  /api/scheduler/preview      → 스케줄 미리보기 (생성 없이)
  GET  /api/scheduler/status       → 현재 진행 상태
"""
import os
import asyncio
import traceback
from datetime import datetime, timezone, timedelta
from typing import Any

from modules.scheduler.time_planner import (
    calculate_schedule,
    count_videos_per_channel,
    get_schedule_summary,
    KST,
)


# 배포 상태 추적
_deploy_status: dict[str, Any] = {
    "running": False,
    "current_date": None,
    "total": 0,
    "completed": 0,
    "failed": 0,
    "current_task": None,
    "results": [],
    "started_at": None,
    "finished_at": None,
}


def get_status() -> dict[str, Any]:
    """현재 배포 상태 반환."""
    return {**_deploy_status}


def preview_schedule(target_date: datetime | None = None) -> dict[str, Any]:
    """스케줄 미리보기 — 영상 생성 없이 시간 배정만 확인."""
    from modules.utils.obsidian_parser import get_today_topics

    if target_date is None:
        target_date = datetime.now(KST)

    result = get_today_topics(target_date=target_date)
    if not result.get("file") or not result.get("topics"):
        return {
            "success": False,
            "message": f"{target_date.strftime('%m-%d')} Day 파일 없음",
        }

    summary = get_schedule_summary(result["topics"], target_date)
    return {
        "success": True,
        "file": result["file"],
        **summary,
    }


async def run_auto_deploy(target_date: datetime | None = None,
                          dry_run: bool = False,
                          max_per_channel: int | None = None) -> dict[str, Any]:
    """자동 배포 실행 — Day 파일 → 영상 생성 → 예약 업로드.

    Args:
        target_date: 배포 날짜 (None이면 오늘)
        dry_run: True면 스케줄만 계산하고 실제 생성/업로드 안 함
        max_per_channel: 채널당 최대 업로드 수 (None이면 전부)

    Returns:
        배포 결과 요약
    """
    global _deploy_status

    if _deploy_status["running"]:
        return {"success": False, "message": "이미 배포가 진행 중입니다"}

    from modules.utils.obsidian_parser import get_today_topics
    from modules.gpt.cutter import generate_cuts

    if target_date is None:
        target_date = datetime.now(KST)

    # 1. Day 파일 파싱
    result = get_today_topics(target_date=target_date)
    if not result.get("file") or not result.get("topics"):
        return {
            "success": False,
            "message": f"{target_date.strftime('%m-%d')} Day 파일 없음",
        }

    # 2. 스케줄 계산
    schedule = calculate_schedule(result["topics"], target_date)

    # 채널당 최대 수 제한
    if max_per_channel:
        channel_count: dict[str, int] = {}
        filtered = []
        for item in schedule:
            ch = item["channel"]
            channel_count[ch] = channel_count.get(ch, 0) + 1
            if channel_count[ch] <= max_per_channel:
                filtered.append(item)
        schedule = filtered

    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "file": result["file"],
            "total": len(schedule),
            "per_channel": count_videos_per_channel(result["topics"]),
            "schedule": [
                {
                    "topic": s["topic"],
                    "channel": s["channel"],
                    "time_kst": s["publish_at_kst"],
                    "publish_at": s["publish_at_iso"],
                }
                for s in schedule
            ],
        }

    # 3. 배포 시작
    _deploy_status = {
        "running": True,
        "current_date": target_date.strftime("%Y-%m-%d"),
        "total": len(schedule),
        "completed": 0,
        "failed": 0,
        "current_task": None,
        "results": [],
        "started_at": datetime.now(KST).isoformat(),
        "finished_at": None,
    }

    try:
        loop = asyncio.get_running_loop()

        for item in schedule:
            topic = item["topic"]
            channel = item["channel"]
            publish_at = item["publish_at_iso"]

            _deploy_status["current_task"] = f"{channel}: {topic}"
            print(f"\n[자동 배포] {channel} — '{topic}' 생성 시작 (예약: {item['publish_at_kst']})")

            task_result = {
                "topic": topic,
                "channel": channel,
                "publish_at": publish_at,
                "status": "pending",
                "error": None,
                "video_path": None,
            }

            try:
                # 3-1. 스크립트 생성 (cutter.py)
                print(f"  [1/4] 스크립트 생성 중...")
                lang_map = {"askanything": "ko", "wonderdrop": "en", "exploratodo": "es", "prismtale": "es"}
                lang = lang_map.get(channel, "ko")

                # lambda 클로저 캡처 문제 방지: 변수를 기본 인수로 바인딩
                cuts, topic_folder, title, tags, description = await loop.run_in_executor(
                    None,
                    lambda _t=topic, _l=lang, _c=channel: generate_cuts(
                        _t,
                        lang=_l,
                        llm_provider="gemini",
                        channel=_c,
                    ),
                )
                print(f"  [1/4] 스크립트 완료: '{title}' ({len(cuts)}컷)")

                # 3-2. 이미지 생성
                print(f"  [2/4] 이미지 생성 중...")
                from modules.image.imagen import generate_image_imagen
                from modules.utils.keys import get_google_key

                image_paths = []
                gemini_keys = os.getenv("GEMINI_API_KEYS", "")
                for i, cut in enumerate(cuts):
                    try:
                        img_key = get_google_key(None, service="imagen", extra_keys=gemini_keys)
                        img_path = generate_image_imagen(
                            cut.get("prompt", ""),
                            i, topic_folder, img_key,
                            gemini_api_keys=gemini_keys,
                            topic=topic,
                        )
                        image_paths.append(img_path)
                    except Exception as img_err:
                        print(f"    컷{i+1} 이미지 실패: {img_err}")
                        image_paths.append(None)

                print(f"  [2/4] 이미지 완료: {sum(1 for p in image_paths if p)}장")

                # 3-3. TTS + 렌더링
                print(f"  [3/4] TTS + 렌더링 중...")
                from modules.tts.elevenlabs import generate_tts
                from modules.transcription.whisper import get_word_timestamps
                from modules.video.remotion import create_remotion_video

                audio_paths = []
                word_timestamps = []
                scripts = []
                for i, cut in enumerate(cuts):
                    script = cut.get("script", "")
                    scripts.append(script)
                    aud = generate_tts(script, i, topic_folder, language=lang)
                    audio_paths.append(aud)
                    if aud:
                        words = get_word_timestamps(aud)
                        word_timestamps.append(words or [])
                    else:
                        word_timestamps.append([])

                # 유효한 컷만 필터
                valid = [(v, a, s, w) for v, a, s, w in
                         zip(image_paths, audio_paths, scripts, word_timestamps)
                         if v and a]

                if not valid:
                    raise RuntimeError("유효한 컷이 없습니다")

                v_paths, a_paths, s_list, w_list = zip(*valid)
                descriptions = [cut.get("description", cut.get("text", "")) for cut in cuts[:len(valid)]]

                video_path = create_remotion_video(
                    list(v_paths), list(a_paths), list(s_list), list(w_list),
                    topic_folder, title=title, channel=channel,
                    descriptions=descriptions,
                )
                print(f"  [3/4] 렌더링 완료: {video_path}")

                # 3-4. YouTube 예약 업로드
                print(f"  [4/4] YouTube 예약 업로드 중... ({item['publish_at_kst']})")
                from modules.upload.youtube import upload_to_youtube
                import json as _json

                # 채널 ID 매칭 (channel_accounts.json)
                _ch_accounts_path = os.path.join("youtube_tokens", "channel_accounts.json")
                _ch_id = None
                if os.path.exists(_ch_accounts_path):
                    with open(_ch_accounts_path, "r") as _f:
                        _accounts = _json.load(_f)
                    _ch_id = _accounts.get(channel, {}).get("youtube")

                tags_clean = [t for t in tags if t.lower() != "#shorts"]
                tag_str = " ".join(tags_clean)
                full_desc = f"{description}\n\n{tag_str}".strip() if description else tag_str

                _video_file = video_path if isinstance(video_path, str) else list(video_path.values())[0]
                yt_result = upload_to_youtube(
                    video_path=_video_file,
                    title=title,
                    description=full_desc,
                    tags=[t.lstrip("#") for t in tags_clean],
                    privacy="private",  # 예약은 private → publishAt
                    publish_at=publish_at,
                    channel_id=_ch_id,
                )

                task_result["status"] = "success"
                task_result["video_path"] = video_path if isinstance(video_path, str) else str(video_path)
                task_result["youtube"] = yt_result
                _deploy_status["completed"] += 1
                print(f"  ✅ 완료: {channel} — '{title}'")

            except Exception as e:
                task_result["status"] = "failed"
                task_result["error"] = str(e)[:200]
                _deploy_status["failed"] += 1
                print(f"  ❌ 실패: {channel} — '{topic}': {e}")
                traceback.print_exc()

            _deploy_status["results"].append(task_result)

    finally:
        _deploy_status["running"] = False
        _deploy_status["current_task"] = None
        _deploy_status["finished_at"] = datetime.now(KST).isoformat()

    return {
        "success": True,
        "total": _deploy_status["total"],
        "completed": _deploy_status["completed"],
        "failed": _deploy_status["failed"],
        "results": _deploy_status["results"],
    }
