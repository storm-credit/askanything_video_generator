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
    - prismtale:   KST 13:30~16 = CET 05:30~08 / EST 00:30~03 (유럽 아침 + US 야간)

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

STATE_FILE = os.path.join("data", "_deploy_state.json")

# TTS 연속 실패 시 조기 중단 임계값
MAX_CONSECUTIVE_TTS_FAILS = 2
CATCHUP_MIN_LEAD_MINUTES = 60
CATCHUP_CHANNEL_STARTS = {
    "prismtale": (19, 0),
    "wonderdrop": (19, 10),
    "exploratodo": (19, 20),
    "askanything": (19, 30),
}
CATCHUP_INTERVAL_MINUTES = 50
UPLOAD_MIN_LEAD_MINUTES = 60


def _round_up_time(dt: datetime, step_minutes: int = 10) -> datetime:
    """지정 간격(step) 단위로 시간을 올림 정렬."""
    dt = dt.replace(second=0, microsecond=0)
    remainder = dt.minute % step_minutes
    if remainder == 0:
        return dt
    return dt + timedelta(minutes=step_minutes - remainder)


def _shift_past_slots_for_today(schedule: list[dict], target_date: datetime) -> list[dict]:
    """오늘 실행인데 이미 지난 예약 슬롯이 있으면 남은 오늘 저녁 슬롯으로 재배치.

    원래 피크 윈도우를 놓친 수동 재실행 케이스용.
    - 미래 슬롯은 그대로 유지
    - 과거 슬롯만 채널별로 저녁 시간대로 재배치
    - 채널 내부 간격은 50분 유지
    """
    target_kst = target_date.astimezone(KST) if target_date.tzinfo else target_date.replace(tzinfo=KST)
    now_kst = datetime.now(KST)
    if target_kst.date() != now_kst.date():
        return schedule

    min_publish_time = _round_up_time(now_kst + timedelta(minutes=CATCHUP_MIN_LEAD_MINUTES))
    past_items: list[dict] = []
    future_items: list[dict] = []

    for item in schedule:
        publish_dt = item.get("publish_at")
        if not isinstance(publish_dt, datetime):
            publish_dt = datetime.fromisoformat(item["publish_at_iso"].replace("Z", "+00:00")).astimezone(KST)
            item["publish_at"] = publish_dt
        if publish_dt >= min_publish_time:
            future_items.append(item)
        else:
            past_items.append(item)

    if not past_items:
        return schedule

    print(f"[자동 배포] 지난 예약 슬롯 {len(past_items)}개 감지 → 오늘 저녁 슬롯으로 재배치")
    channel_counts: dict[str, int] = {}

    for item in sorted(past_items, key=lambda x: (x["channel"], x.get("order", 0))):
        channel = item["channel"]
        start_hour, start_minute = CATCHUP_CHANNEL_STARTS.get(channel, (19, 30))
        channel_base = now_kst.replace(hour=start_hour, minute=start_minute, second=0, microsecond=0)
        slot_index = channel_counts.get(channel, 0)
        publish_dt = max(channel_base, min_publish_time) + timedelta(minutes=CATCHUP_INTERVAL_MINUTES * slot_index)
        publish_utc = publish_dt.astimezone(timezone.utc)
        item["publish_at"] = publish_dt
        item["publish_at_kst"] = publish_dt.strftime("%Y-%m-%d %H:%M KST")
        item["publish_at_iso"] = publish_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        channel_counts[channel] = slot_index + 1

    merged = future_items + past_items
    merged.sort(key=lambda x: x["publish_at"])
    return merged


def _ensure_future_publish_at(publish_at_iso: str, channel: str) -> str:
    """업로드 직전에 예약 시간이 지났으면 오늘 남은 시간대로 재조정."""
    try:
        scheduled_dt = datetime.fromisoformat(publish_at_iso.replace("Z", "+00:00")).astimezone(KST)
    except Exception:
        return publish_at_iso

    now_kst = datetime.now(KST)
    min_publish_time = _round_up_time(now_kst + timedelta(minutes=UPLOAD_MIN_LEAD_MINUTES))
    if scheduled_dt >= min_publish_time:
        return publish_at_iso

    adjusted_kst = min_publish_time
    if adjusted_kst.date() != now_kst.date():
        # 오늘 안에 넣을 수 있으면 최대한 오늘 마지막 슬롯으로 보정.
        today_last = now_kst.replace(hour=23, minute=50, second=0, microsecond=0)
        if today_last >= min_publish_time:
            adjusted_kst = today_last

    adjusted_utc = adjusted_kst.astimezone(timezone.utc)
    adjusted_iso = adjusted_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    print(
        f"[자동 배포] 예약 시간 보정: {channel} "
        f"{scheduled_dt.strftime('%Y-%m-%d %H:%M KST')} → {adjusted_kst.strftime('%Y-%m-%d %H:%M KST')}"
    )
    return adjusted_iso


def _preflight_tts() -> bool:
    """TTS 서버 헬스체크 — 배치 시작 전 연결 확인."""
    import requests
    tts_url = os.getenv("QWEN3_TTS_URL", "http://localhost:8010")
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


async def _read_sse_response(response, on_line) -> None:
    """HTTP SSE 응답을 한 줄씩 읽어 콜백에 전달."""
    async for line in response.aiter_lines():
        if not line.startswith("data:"):
            continue
        raw = line[5:].strip()
        if raw:
            await on_line(raw)


async def _prepare_render_upload_via_preview_flow(
    *,
    client,
    api_port: str,
    topic: str,
    language: str,
    channel: str,
    format_type: str | None,
    publish_at: str,
    series_title: str | None,
) -> dict[str, Any]:
    """웹 미리보기 플로우와 동일하게 prepare → render → upload를 순차 실행."""
    preview_payload = {
        "topic": topic,
        "language": language,
        "channel": channel,
        "formatType": format_type,
        "imageEngine": "imagen",
        "videoEngine": "none",
        "llmProvider": "gemini",
        "geminiKeys": os.getenv("GEMINI_API_KEYS", ""),
    }
    preview_data: dict[str, Any] | None = None

    async def on_prepare_line(raw: str) -> None:
        nonlocal preview_data
        if raw.startswith("PREVIEW|"):
            preview_data = json.loads(raw[8:])
        elif raw.startswith("ERROR|"):
            raise RuntimeError(raw[6:].strip())
        elif not raw.startswith("PROG|"):
            print(f"  [미리보기] {raw.rstrip()}")

    async with client.stream(
        "POST",
        f"http://127.0.0.1:{api_port}/api/prepare",
        json=preview_payload,
        headers={"Accept": "text/event-stream"},
    ) as response:
        if response.status_code >= 400:
            body = (await response.aread()).decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"[미리보기 오류] HTTP {response.status_code}: {body or response.reason_phrase}")
        await _read_sse_response(response, on_prepare_line)

    if not preview_data or not preview_data.get("sessionId"):
        raise RuntimeError("[미리보기 오류] PREVIEW 세션을 받지 못했습니다.")

    session_id = preview_data["sessionId"]
    cuts = preview_data.get("cuts") or []
    if not cuts:
        raise RuntimeError("[미리보기 오류] 컷 데이터가 비어 있습니다.")

    render_payload = {
        "sessionId": session_id,
        "cuts": [{"index": c.get("index", i), "script": c.get("script", "")} for i, c in enumerate(cuts)],
        "videoEngine": "veo3",
        "videoModel": "hero-only",
        "cameraStyle": "auto",
        "bgmTheme": "random",
        "formatType": format_type,
        "channel": channel,
        "platforms": ["youtube"],
        "ttsSpeed": 1.05,
        "voiceId": "auto",
    }
    try:
        from modules.utils.channel_config import get_channel_preset as _get_preset
        _preset = _get_preset(channel)
        if _preset and _preset.get("tts_speed"):
            render_payload["ttsSpeed"] = _preset["tts_speed"]
    except Exception:
        pass
    video_path = ""

    async def on_render_line(raw: str) -> None:
        nonlocal video_path
        if raw.startswith("DONE|"):
            video_path = raw[5:].split("|")[0].strip()
            print(f"  [렌더] 완료: {video_path}")
        elif raw.startswith("ERROR|"):
            raise RuntimeError(raw[6:].strip())
        elif not raw.startswith("PROG|"):
            print(f"  [렌더] {raw.rstrip()}")

    async with client.stream(
        "POST",
        f"http://127.0.0.1:{api_port}/api/render",
        json=render_payload,
        headers={"Accept": "text/event-stream"},
    ) as response:
        if response.status_code >= 400:
            body = (await response.aread()).decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"[렌더 오류] HTTP {response.status_code}: {body or response.reason_phrase}")
        await _read_sse_response(response, on_render_line)

    if not video_path:
        raise RuntimeError("[렌더 오류] 최종 영상 경로를 받지 못했습니다.")

    abs_video_path = os.path.abspath(video_path.lstrip("/"))
    title = preview_data.get("title") or topic
    description = preview_data.get("description") or ""
    raw_tags = [str(t).lstrip("#") for t in (preview_data.get("tags") or []) if str(t).strip()]
    tags: list[str] = []
    seen_tags: set[str] = set()
    for candidate in [channel, language, *raw_tags]:
        value = str(candidate or "").lstrip("#").strip()
        lowered = value.lower()
        if not value or lowered in seen_tags:
            continue
        seen_tags.add(lowered)
        tags.append(value)
    tags = tags[:5]

    from modules.upload.youtube import upload_video as yt_upload
    from modules.utils.channel_config import get_upload_account

    publish_at = _ensure_future_publish_at(publish_at, channel)
    sched_dt = datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
    if sched_dt.tzinfo is None:
        sched_dt = sched_dt.replace(tzinfo=timezone.utc)
    yt_publish_at = sched_dt.isoformat()
    account_id = get_upload_account(channel, "youtube")
    print(f"  [업로드] YouTube 예약 업로드 시작... ({yt_publish_at})")
    yt_result = await asyncio.get_running_loop().run_in_executor(
        None,
        lambda: yt_upload(
            video_path=abs_video_path,
            title=title,
            description=description,
            tags=tags,
            privacy="private",
            channel_id=account_id,
            publish_at=yt_publish_at,
            format_type=format_type,
            series_title=series_title,
            channel=channel,
        ),
    )
    if not yt_result.get("success"):
        raise RuntimeError(f"YouTube 업로드 실패: {yt_result.get('error', 'unknown')}")

    return {
        "video_path": video_path,
        "youtube_url": f"{yt_result.get('url', '')} (예약: {yt_publish_at})",
        "publish_at": publish_at,
        "title": title,
        "cut_count": len(cuts),
        "tts_chars": sum(len(str(c.get("script", ""))) for c in cuts),
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
    base_schedule = calculate_schedule(result["topics"], target_date)
    adjusted_schedule = _shift_past_slots_for_today(base_schedule, target_date)
    if adjusted_schedule != base_schedule:
        summary["schedule"] = [
            {
                "topic": s["topic"],
                "channel": s["channel"],
                "time_kst": s["publish_at_kst"],
                "publish_at": s["publish_at_iso"],
            }
            for s in adjusted_schedule
        ]
        summary["table"] = "\n".join(
            ["시간 (KST)     | 채널           | 주제", "-" * 60]
            + [
                f"{s['publish_at_kst'].split(' ')[1]}        | {s['channel'][:15].ljust(15)} | {s['topic'][:30]}"
                for s in adjusted_schedule
            ]
        )
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

    schedule = _shift_past_slots_for_today(schedule, target_date)

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
    # Preserve previous results for crash recovery
    _prev_results = []
    try:
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                prev = json.load(f)
            if prev.get("current_date") == date_str:
                _prev_results = [r for r in prev.get("results", []) if r.get("status") == "success"]
    except Exception:
        pass

    _deploy_status = {
        "running": True,
        "current_date": date_str,
        "total": len(schedule),
        "completed": len(completed_keys),
        "failed": 0,
        "current_task": None,
        "results": _prev_results,
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
            task_result["_retries"] = item.get("_retries", 0)

            try:
                # 웹 미리보기 경로와 동일한 파이프라인 사용:
                # prepare(기획+이미지 세션) → render(TTS+Veo+Remotion) → upload(예약)
                import httpx

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

                api_port = os.getenv("API_PORT", "8003")

                async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
                    flow_result = await _prepare_render_upload_via_preview_flow(
                        client=client,
                        api_port=api_port,
                        topic=_topic_for_llm,
                        language=lang,
                        channel=channel,
                        format_type=_fmt,
                        publish_at=publish_at,
                        series_title=job.get("series_title"),
                    )

                task_result["status"] = "success"
                consecutive_tts_fails = 0
                task_result["publish_at"] = flow_result.get("publish_at", publish_at)
                task_result["video_path"] = flow_result.get("video_path", "")
                task_result["youtube"] = {"url": flow_result.get("youtube_url", "")}
                task_result["format_type"] = _fmt or job.get("format_type", "FACT")
                task_result["cut_count"] = flow_result.get("cut_count")
                try:
                    from modules.utils.cost_tracker import record_generation_cost

                    record_generation_cost(
                        channel=channel,
                        success=True,
                    )
                except Exception as cost_exc:
                    print(f"  [비용 추적] 기록 실패(무시): {cost_exc}")
                _deploy_status["completed"] += 1
                _deploy_status["results"].append(task_result)
                _save_state()
                _display_title = flow_result.get("title") or topic
                print(f"  ✅ 완료: {channel} — '{_display_title}'")
                # Day 파��� 체크박스
                if day_file_path:
                    topic_group = job.get("topic_group", "")
                    if topic_group:
                        group_total = sum(1 for s in schedule if s.get("topic_group") == topic_group)
                        group_success = sum(1 for r in _deploy_status["results"] if r.get("topic_group") == topic_group and r.get("status") == "success")
                        if group_success >= group_total:
                            try:
                                from modules.utils.obsidian_parser import tick_topic_done
                                if tick_topic_done(day_file_path, topic_group):
                                    print(f"  📋 Day 파일 체크: ✅ {topic_group[:30]}")
                            except Exception:
                                pass
                # 비용은 /api/generate 내부에서 자동 기록됨 — 알림만 전송
                try:
                    from modules.utils.notify import notify_success
                    notify_success(
                        channel,
                        f"[{channel}] {_display_title}",
                        video_url=flow_result.get("youtube_url", ""),
                    )
                except Exception:
                    pass

            except Exception as e:
                err_str = str(e)[:200]
                is_retryable = any(k in err_str.lower() for k in ["429", "timeout", "resource_exhausted", "rate limit", "connection"])

                if is_retryable and task_result.get("_retries", 0) < 2:
                    retry_num = task_result.get("_retries", 0) + 1
                    wait_sec = 30 * (2 ** (retry_num - 1))
                    print(f"  ⏳ 리트라이 — {wait_sec}초 후 재시도 ({retry_num}/2): {err_str}")
                    await asyncio.sleep(wait_sec)
                    task_result["_retries"] = retry_num
                    schedule.append({**item, "_retries": retry_num})
                    continue

                task_result["status"] = "failed"
                task_result["error"] = err_str
                task_result["format_type"] = job.get("format_type", "FACT")
                _deploy_status["failed"] += 1
                print(f"  ❌ 실패: {channel} — '{topic}': {e}")

                # TTS 연속 실패 감지
                _tts_patterns = ["오디오 실패", "tts", "elevenlabs", "qwen3", "audio"]
                if any(p in err_str.lower() for p in _tts_patterns):
                    consecutive_tts_fails += 1
                    if consecutive_tts_fails >= MAX_CONSECUTIVE_TTS_FAILS:
                        _notify_batch_abort(f"TTS {consecutive_tts_fails}회 연속 실패 — 배치 중단")
                        _deploy_status["results"].append(task_result)
                        raise RuntimeError(f"TTS {consecutive_tts_fails}회 연속 실패 — 조기 중단")
                else:
                    consecutive_tts_fails = 0

                traceback.print_exc()
                try:
                    from modules.utils.notify import notify_failure
                    notify_failure(channel, topic, error=err_str)
                except Exception:
                    pass

            if task_result.get("status") != "success":
                _deploy_status["results"].append(task_result)
            _save_state()

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
