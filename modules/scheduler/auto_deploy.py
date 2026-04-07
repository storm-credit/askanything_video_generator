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
import json
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

STATE_FILE = os.path.join("assets", "_deploy_state.json")


def _save_state():
    """배포 상태를 파일로 저장 — 원자적 쓰기 (크래시 안전)."""
    import tempfile
    try:
        state_dir = os.path.dirname(STATE_FILE) or "."
        os.makedirs(state_dir, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=state_dir, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(_deploy_status, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, STATE_FILE)
    except Exception as e:
        print(f"[자동 배포] 상태 저장 실패: {e}")
        if 'tmp_path' in locals() and os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _load_state(target_date_str: str) -> set[str]:
    """이전 배포에서 완료된 토픽 목록 로드 — 중복 생성 방지."""
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            # 같은 날짜의 이전 배포 결과만 사용
            if state.get("current_date") == target_date_str:
                completed = set()
                for r in state.get("results", []):
                    if r.get("status") == "success":
                        completed.add(f"{r['channel']}:{r['topic']}")
                if completed:
                    print(f"[자동 배포] 이전 배포에서 {len(completed)}개 완료 토픽 발견 → 스킵")
                return completed
    except Exception as e:
        print(f"[자동 배포] 상태 로드 실패 (무시): {e}")
    return set()


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

    # 3. 배포 시작 — 이전 완료 토픽 로드
    date_str = target_date.strftime("%Y-%m-%d")
    completed_keys = _load_state(date_str)

    _deploy_status = {
        "running": True,
        "current_date": date_str,
        "total": len(schedule),
        "completed": 0,
        "failed": 0,
        "current_task": None,
        "results": [],
        "started_at": datetime.now(KST).isoformat(),
        "finished_at": None,
    }
    _save_state()

    try:
        loop = asyncio.get_running_loop()

        for item in schedule:
            # 중복 방지: 이전 배포에서 성공한 토픽 스킵
            item_key = f"{item['channel']}:{item['topic']}"
            if item_key in completed_keys:
                print(f"[자동 배포] 스킵 (이미 완료): {item['channel']} — '{item['topic']}'")
                _deploy_status["completed"] += 1
                continue
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

                # 토픽명: 채널 언어에 맞는 제목 사용 (한국어 토픽이 EN/ES에 들어가면 LLM 혼동)
                _item_title = item.get("title", "")
                _topic_for_llm = _item_title if (_item_title and _item_title != topic and lang != "ko") else topic

                # lambda 클로저 캡처 문제 방지: 변수를 기본 인수로 바인딩
                cuts, topic_folder, title, tags, description = await loop.run_in_executor(
                    None,
                    lambda _t=_topic_for_llm, _l=lang, _c=channel: generate_cuts(
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
                    # 감정 태그 추출
                    _desc = cut.get("description", cut.get("text", ""))
                    _emo = None
                    for _et in ["SHOCK","WONDER","TENSION","REVEAL","URGENCY","DISBELIEF","IDENTITY","CALM"]:
                        if f"[{_et}]" in _desc:
                            _emo = _et
                            break
                    aud = generate_tts(script, i, topic_folder, language=lang, emotion=_emo, channel=channel)
                    audio_paths.append(aud)
                    if aud:
                        words = get_word_timestamps(aud, language=lang)
                        # Whisper 재인식 오류 보정: 원본 스크립트로 매핑
                        from modules.transcription.whisper import align_words_with_script
                        words = align_words_with_script(words or [], script)
                        word_timestamps.append(words)
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
                # 텔레그램 알림
                try:
                    from modules.utils.notify import notify_success
                    _yt_url = (yt_result or {}).get("url", "")
                    notify_success(channel, title, video_url=_yt_url)
                except Exception:
                    pass

            except Exception as e:
                err_str = str(e)[:200]
                is_retryable = any(k in err_str.lower() for k in ["429", "timeout", "resource_exhausted", "rate limit", "connection"])

                if is_retryable and task_result.get("_retries", 0) < 2:
                    retry_num = task_result.get("_retries", 0) + 1
                    wait_sec = 30 * (2 ** (retry_num - 1))  # 30s, 60s
                    print(f"  ⏳ 리트라이 가능 에러 — {wait_sec}초 후 재시도 ({retry_num}/2): {err_str}")
                    await asyncio.sleep(wait_sec)
                    task_result["_retries"] = retry_num
                    # 스케줄 맨 뒤에 다시 추가
                    schedule.append({**item, "_retries": retry_num})
                    continue  # results에 추가하지 않고 다음으로

                task_result["status"] = "failed"
                task_result["error"] = err_str
                _deploy_status["failed"] += 1
                print(f"  ❌ 실패: {channel} — '{topic}': {e}")
                traceback.print_exc()
                # 텔레그램 실패 알림
                try:
                    from modules.utils.notify import notify_failure
                    notify_failure(channel, topic, error=err_str)
                except Exception:
                    pass

            _deploy_status["results"].append(task_result)
            _save_state()  # 매 토픽 완료 후 상태 저장

    finally:
        _deploy_status["running"] = False
        _deploy_status["current_task"] = None
        _deploy_status["finished_at"] = datetime.now(KST).isoformat()
        _save_state()  # 최종 상태 저장
        # 일일 배포 요약 알림
        try:
            from modules.utils.notify import notify_deploy_summary
            notify_deploy_summary(
                _deploy_status["total"], _deploy_status["completed"],
                _deploy_status["failed"], date_str,
            )
        except Exception:
            pass

    return {
        "success": True,
        "total": _deploy_status["total"],
        "completed": _deploy_status["completed"],
        "failed": _deploy_status["failed"],
        "results": _deploy_status["results"],
    }
