"""자동 배포 스케줄러 — Day 파일 → 영상 생성 → 예약 업로드 파이프라인.

흐름:
  1. Day 파일 파싱 → 채널별 주제 추출
  2. 채널별 업로드 시간 자동 계산 (time_planner)
  3. 주제별 cutter.py → 이미지 → TTS → 렌더링
  4. YouTube 예약 업로드 (publishAt)

시간 설계:
  배치 실행: KST 02:00~06:00 (새벽 — API 사용량 최소, 429 회피)
  예약 공개: 채널별 피크 타임 (time_planner.py CHANNEL_WINDOWS)
    - askanything: KST 21~23:30 (한국 저녁)
    - wonderdrop:  KST 08~11 = EST 19~22 (미국 저녁)
    - exploratodo: KST 10~13 = CST 20~23 (멕시코 저녁)
    - prismtale:   KST 08~11 = EST 19~22 (US 히스패닉 저녁)

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

# TTS 연속 실패 시 조기 중단 임계값
MAX_CONSECUTIVE_TTS_FAILS = 2


def _preflight_tts() -> bool:
    """TTS 서버 헬스체크 — 배치 시작 전 연결 확인."""
    import requests
    tts_url = os.getenv("QWEN3_TTS_URL", "http://host.docker.internal:8010")
    try:
        resp = requests.get(f"{tts_url}/health", timeout=5)
        if resp.status_code == 200:
            print("[사전 체크] ✅ TTS 서버 정상")
            return True
    except Exception:
        pass
    # /health 없으면 root 체크
    try:
        resp = requests.get(tts_url, timeout=5)
        if resp.status_code < 500:
            print("[사전 체크] ✅ TTS 서버 응답 확인")
            return True
    except Exception:
        pass
    print("[사전 체크] ❌ TTS 서버 연결 불가")
    return False


def _notify_batch_abort(reason: str):
    """배치 중단 알림 — Telegram."""
    try:
        from modules.utils.notify import _send
        _send(f"🛑 <b>배치 중단</b>\n{reason}\n⏰ {datetime.now(KST).strftime('%H:%M')}")
    except Exception:
        print(f"[배치 중단] {reason}")


def _reorder_by_topic_group(schedule: list[dict]) -> list[dict]:
    """주제별 그룹핑 — 같은 주제의 채널을 연속 배치.

    기존: publish_at 시간순 (채널 뒤섞임)
    변경: 주제1(4채널) → 주제2(4채널) → 주제3(4채널)
    채널 순서: askanything → wonderdrop → exploratodo → prismtale
    """
    channel_order = {"askanything": 0, "wonderdrop": 1, "exploratodo": 2, "prismtale": 3}
    groups: dict[str, list[dict]] = {}
    group_order: list[str] = []

    for item in schedule:
        key = item.get("topic_group", item.get("topic", "unknown"))
        if key not in groups:
            groups[key] = []
            group_order.append(key)
        groups[key].append(item)

    reordered = []
    for key in group_order:
        items = sorted(groups[key], key=lambda x: channel_order.get(x.get("channel", ""), 99))
        reordered.extend(items)

    print(f"[스케줄] 주제별 그룹핑: {len(group_order)}주제 × {len(schedule)//max(len(group_order),1)}채널")
    return reordered


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
    from modules.orchestrator.orchestrator import MainOrchestrator
    from modules.orchestrator.base import AgentContext

    if target_date is None:
        target_date = datetime.now(KST)

    # 1. Day 파일 파싱
    result = get_today_topics(target_date=target_date)
    if not result.get("file") or not result.get("topics"):
        return {
            "success": False,
            "message": f"{target_date.strftime('%m-%d')} Day 파일 없음",
        }

    day_file_path: str | None = result.get("file_path")

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

    # 3. 사전 헬스체크 — TTS 서버 연결 확인
    tts_ok = _preflight_tts()
    if not tts_ok:
        _notify_batch_abort("TTS 서버(Qwen3) 연결 불가 — 배치 중단")
        return {"success": False, "message": "TTS 서버 연결 불가. Docker 확인 필요."}

    # 4. 주제별 그룹핑 — 같은 주제의 채널들을 연속 처리
    schedule = _reorder_by_topic_group(schedule)

    # 5. 배포 시작 — 이전 완료 토픽 로드
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

    consecutive_tts_fails = 0  # TTS 연속 실패 카운터

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

            job = item  # alias for clarity
            task_result = {
                "topic": topic,
                "channel": channel,
                "topic_group": item.get("topic_group", topic),
                "publish_at": publish_at,
                "status": "pending",
                "error": None,
                "video_path": None,
            }

            try:
                # v2 오케스트라: 전체 파이프라인을 에이전트 시스템으로 실행
                lang_map = {"askanything": "ko", "wonderdrop": "en", "exploratodo": "es", "prismtale": "es"}
                lang = lang_map.get(channel, "ko")

                _item_title = item.get("title", "")
                _topic_for_llm = _item_title if (_item_title and _item_title != topic and lang != "ko") else topic

                # 포맷 3단계 폴백: Day명시 → 키워드감지 → 채널선호
                _fmt = job.get("format_type")
                _fmt_src = "Day명시" if _fmt else None
                if not _fmt:
                    from modules.gpt.prompts.formats import detect_format_type
                    _fmt = detect_format_type(topic, lang)
                    if _fmt:
                        _fmt_src = "키워드"
                if not _fmt:
                    from modules.utils.channel_config import get_channel_preset as _gcp
                    _preferred = (_gcp(channel) or {}).get("preferred_formats", [])
                    if _preferred:
                        import random as _random
                        _fmt = _random.choice(_preferred)
                        _fmt_src = "채널선호"
                if _fmt:
                    print(f"  [포맷 선택] {channel}: {_fmt} (출처: {_fmt_src})")

                ctx = AgentContext(
                    topic=_topic_for_llm,
                    language=lang,
                    channel=channel,
                    image_engine="imagen",
                    image_model="imagen-4.0-generate-001",  # Standard 고정
                    video_engine="veo3",
                    video_model="hero-only",  # SHOCK/REVEAL만 영상 (비용 절감)
                    format_type=_fmt,  # 3단계 폴백 적용
                    series_title=job.get("series_title"),  # 시리즈 태그 전달
                    publish_mode="scheduled",
                    scheduled_time=publish_at,
                    gemini_keys_override=os.getenv("GEMINI_API_KEYS", ""),
                )

                orchestrator = MainOrchestrator()
                yt_url = ""

                async for msg in orchestrator.run(ctx):
                    # SSE 메시지에서 핵심 이벤트 추출
                    if msg.startswith("UPLOAD_DONE|youtube|"):
                        yt_url = msg.split("|", 2)[2].strip()
                    elif msg.startswith("ERROR|"):
                        raise RuntimeError(msg[6:].strip())
                    # 진행 로그 출력
                    if not msg.startswith("PROG|"):
                        print(f"  {msg.rstrip()}")

                task_result["status"] = "success"
                consecutive_tts_fails = 0  # 성공 시 카운터 리셋
                task_result["video_path"] = str(ctx.video_paths) if ctx.video_paths else None
                task_result["youtube"] = {"url": yt_url} if yt_url else None
                task_result["format_type"] = job.get("format_type", "FACT")
                _deploy_status["completed"] += 1
                print(f"  ✅ 완료: {channel} — '{ctx.title}'")
                # Day 파일 체크박스: 같은 topic_group의 모든 채널이 완료되면 ✅ 표시
                if day_file_path:
                    topic_group = job.get("topic_group", "")
                    if topic_group:
                        # 이 topic_group에서 예상 채널 수
                        group_total = sum(1 for s in schedule if s.get("topic_group") == topic_group)
                        # 기존 결과에서 성공 수 (현재 포함)
                        group_success = sum(1 for r in _deploy_status["results"] if r.get("topic_group") == topic_group and r.get("status") == "success")
                        if group_success + 1 >= group_total:
                            try:
                                from modules.utils.obsidian_parser import tick_topic_done
                                if tick_topic_done(day_file_path, topic_group):
                                    print(f"  📋 Day 파일 체크: ✅ {topic_group[:30]}")
                            except Exception:
                                pass
                # 비용 기록 + 텔레그램 알림
                try:
                    from modules.utils.cost_tracker import record_generation_cost
                    from modules.utils.notify import notify_success, notify_cost
                    cost_entry = record_generation_cost(
                        channel=channel, success=True,
                        llm_usd=ctx.total_cost(),
                        image_count=ctx.image_count,
                        video_count=ctx.video_count,
                        tts_chars=ctx.tts_chars,
                    )
                    notify_success(channel, ctx.title, video_url=yt_url)
                    notify_cost(channel, ctx.title, cost_entry, video_url=yt_url,
                                format_type=job.get("format_type", ""))
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
                task_result["format_type"] = job.get("format_type", "FACT")
                _deploy_status["failed"] += 1
                print(f"  ❌ 실패: {channel} — '{topic}': {e}")

                # TTS 전체 실패 감지 → 연속 실패 시 배치 조기 중단
                if "오디오 실패" in err_str and "전체" in err_str or err_str.count("오디오 실패") > 0:
                    consecutive_tts_fails += 1
                    if consecutive_tts_fails >= MAX_CONSECUTIVE_TTS_FAILS:
                        _notify_batch_abort(f"TTS {consecutive_tts_fails}회 연속 실패 — 서버 문제 추정, 배치 중단")
                        _deploy_status["results"].append(task_result)
                        raise RuntimeError(f"TTS {consecutive_tts_fails}회 연속 실패 — 조기 중단")
                else:
                    consecutive_tts_fails = 0  # TTS 이외 에러면 리셋
                # 실패 시에도 부분 비용 기록
                try:
                    from modules.utils.cost_tracker import record_generation_cost
                    record_generation_cost(
                        channel=channel, success=False,
                        llm_usd=ctx.total_cost() if "ctx" in dir() else 0.0,
                        image_count=ctx.image_count if "ctx" in dir() else 0,
                        video_count=ctx.video_count if "ctx" in dir() else 0,
                        tts_chars=ctx.tts_chars if "ctx" in dir() else 0,
                    )
                except Exception:
                    pass
                traceback.print_exc()
                # FailureAnalyzer: 실패 분류 + 로그 + 텔레그램 상세 알림
                try:
                    from modules.orchestrator.agents.failure_analyzer import analyze_and_notify
                    analyze_and_notify(channel, topic, err_str)
                except Exception:
                    # 폴백: 기존 알림
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
