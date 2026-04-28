"""자동 배포 스케줄러 — Day 파일 → 영상 생성 → 예약 업로드 파이프라인.

흐름:
  1. Day 파일 파싱 → 채널별 주제 추출
  2. 채널별 업로드 시간 자동 계산 (time_planner)
  3. 주제별 cutter.py → 이미지 → TTS → 렌더링
  4. YouTube 예약 업로드 (publishAt)

시간 설계:
  배치 실행: KST 02:00~06:00 (새벽 — API 사용량 최소, 429 회피)
  예약 공개: 채널별 피크 타임 (time_planner.py CHANNEL_WINDOWS)
    - askanything: KST 19:30~22:00 (한국 저녁)
    - wonderdrop:  KST 08:00~10:30 = EDT 19:00~21:30 (미국 저녁)
    - exploratodo: KST 11:00~13:30 = CDT 21:00~23:30 (라탐 저녁)
    - prismtale:   KST 07:30~09:30 = EDT 18:30~20:30 (US Hispanic 저녁)
  채널별 하루 상한을 넘는 예약은 자동으로 다음날로 이월한다.

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
import re
import traceback
from datetime import datetime, timezone, timedelta
from typing import Any

from modules.scheduler.time_planner import (
    calculate_schedule,
    count_videos_per_channel,
    format_schedule_table,
    summarize_schedule_counts,
    _get_daily_capacity,
    _get_window_bounds,
    _schedule_channel_items,
    CHANNEL_WINDOWS,
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
DEPLOY_LOCK_FILE = os.path.join("data", "_deploy.lock")

# TTS 연속 실패 시 조기 중단 임계값
MAX_CONSECUTIVE_TTS_FAILS = 2
CATCHUP_MIN_LEAD_MINUTES = 60
UPLOAD_MIN_LEAD_MINUTES = 60
DEPLOY_LOCK_TTL_SECONDS = 12 * 60 * 60
SLOT_SEARCH_DAYS = 14
_COUNTDOWN_CUE_PATTERN = re.compile(
    r"(?i)\btop\s*\d+\b|#\d+\b|\b(?:ranking|ranked|tier list|clasificación|랭킹|순위)\b"
)
_WHO_WINS_QUESTION_PATTERN = re.compile(
    r"(?i)\bwho(?:\s+\w+){0,2}\s+wins?\b|qui[eé]n\s+ganar[ií]a(?:\s+de\s+verdad)?\b|누가\s*(?:진짜\s*)?(?:이겨|더\s*강해)"
)


def _pick_retry_topic_for_hard_fail(item: dict[str, Any], topic: str, lang: str) -> str | None:
    """HARD FAIL 시 한 번 더 시도할 대체 LLM 주제를 고른다.

    기본 주제(topic_group)가 넓어서 반복 표현이 생기는 경우,
    채널별 제목(title)로 좁혀 재생성을 유도한다.
    """
    title = str(item.get("title") or "").strip()
    format_type = str(item.get("format_type") or "").upper().strip()

    if format_type == "COUNTDOWN":
        retry_topic = _strip_countdown_cues(title or topic)
        if retry_topic and retry_topic != topic:
            return retry_topic

    if not title or title == topic:
        return None
    return title


def _strip_countdown_cues(text: str) -> str:
    """TOP N/랭킹 신호를 일반 reveal 제목으로 정리한다."""
    if not text:
        return text

    cleaned = _COUNTDOWN_CUE_PATTERN.sub("", text)
    cleaned = re.sub(r"(?i)\bmost\b", "", cleaned)
    cleaned = re.sub(r"(?i)\bm[aá]s\b", "", cleaned)
    cleaned = re.sub(r"\s*[,/|-]\s*", ": ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+([:?!])", r"\1", cleaned)
    cleaned = re.sub(r":\s*:", ": ", cleaned)
    return cleaned.strip(" ,:-")


def _soften_who_wins_cues(text: str, lang: str) -> str:
    """직접 대결 신호를 비교/차이형 제목으로 약화한다."""
    if not text:
        return text

    connector = "와" if lang == "ko" else "y" if lang == "es" else "and"
    cleaned = re.sub(r"(?i)\s+\bvs\.?\b\s+", f" {connector} ", text)
    cleaned = re.sub(r"(?i)\s+\bversus\b\s+", f" {connector} ", cleaned)
    cleaned = _WHO_WINS_QUESTION_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\s*[,/|-]\s*", ": ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+([:?!])", r"\1", cleaned)
    cleaned = re.sub(r":\s*:", ": ", cleaned)
    return cleaned.strip(" ,:-?")


def _normalize_format_for_channel(channel: str, format_type: str | None) -> tuple[str | None, str | None]:
    """채널별 금지 포맷을 안전한 선호 포맷으로 치환한다."""
    try:
        from modules.utils.channel_config import normalize_format_for_channel as _normalize
        return _normalize(channel, format_type)
    except Exception:
        return format_type, None


def _round_up_time(dt: datetime, step_minutes: int = 10) -> datetime:
    """지정 간격(step) 단위로 시간을 올림 정렬."""
    dt = dt.replace(second=0, microsecond=0)
    remainder = dt.minute % step_minutes
    if remainder == 0:
        return dt
    return dt + timedelta(minutes=step_minutes - remainder)


def _parse_publish_at_kst(publish_at_iso: str) -> datetime | None:
    """ISO publishAt 문자열을 KST datetime으로 변환."""
    try:
        return datetime.fromisoformat(publish_at_iso.replace("Z", "+00:00")).astimezone(KST)
    except Exception:
        return None


def _build_rollout_notes(schedule: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """스케줄 항목에서 lead-channel-first 보류 메타를 추출한다."""
    notes: list[dict[str, Any]] = []
    seen: set[tuple[str, str, tuple[str, ...]]] = set()

    for item in schedule:
        if str(item.get("rollout_strategy") or "").strip() != "lead_channel_first":
            continue
        topic_group = str(item.get("topic_group") or item.get("topic") or "").strip()
        lead_channel = str(item.get("lead_channel") or item.get("channel") or "").strip()
        holdback_channels = [
            str(channel).strip()
            for channel in (item.get("holdback_channels") or [])
            if str(channel).strip()
        ]
        if not topic_group or not lead_channel or not holdback_channels:
            continue
        key = (topic_group, lead_channel, tuple(holdback_channels))
        if key in seen:
            continue
        seen.add(key)
        notes.append({
            "topic_group": topic_group,
            "lead_channel": lead_channel,
            "holdback_channels": holdback_channels,
        })
    return notes


def _serialize_schedule(schedule: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "topic": item["topic"],
            "channel": item["channel"],
            "time_kst": item["publish_at_kst"],
            "publish_at": item["publish_at_iso"],
            "day_offset": item.get("day_offset", 0),
            "rollout_strategy": item.get("rollout_strategy"),
            "lead_channel": item.get("lead_channel"),
            "holdback_channels": item.get("holdback_channels", []),
        }
        for item in schedule
    ]


def _build_schedule_response(
    *,
    file_name: str,
    topics: list[dict[str, Any]],
    schedule: list[dict[str, Any]],
    target_date: datetime,
) -> dict[str, Any]:
    """preview/dry-run 공용 스케줄 응답."""
    target_kst = target_date.astimezone(KST) if target_date.tzinfo else target_date.replace(tzinfo=KST)
    rollout_notes = _build_rollout_notes(schedule)
    count_summary = summarize_schedule_counts(
        schedule,
        target_kst,
        requested_counts=count_videos_per_channel(topics),
        rollout_notes=rollout_notes,
    )
    return {
        "success": True,
        "file": file_name,
        "date": target_kst.strftime("%Y-%m-%d"),
        "total_videos": len(schedule),
        "total": len(schedule),
        "per_channel": count_summary["public_scheduled_per_channel"],
        "channel_summary": {
            "target": count_summary["requested_per_channel"],
            "scheduled": count_summary["public_scheduled_per_channel"],
            "rollout_holdback": count_summary["holdback_per_channel"],
            "final_expected": count_summary["final_expected_per_channel"],
            "publish_on_date": count_summary["publish_on_target_date_per_channel"],
            "carryover_next_days": count_summary["carryover_next_days_per_channel"],
        },
        "publish_dates": count_summary["publish_dates"],
        "rollout_overview": count_summary["rollout_overview"],
        "rollout": rollout_notes,
        "schedule": _serialize_schedule(schedule),
        "table": format_schedule_table(schedule),
    }


def _resolve_source_file_path(source_file: str | None, *, task_date: str | None = None) -> str | None:
    """basename 형태 source_file을 실제 Day 파일 경로로 복원한다."""
    raw = str(source_file or "").strip()
    if not raw:
        return None
    if os.path.exists(raw):
        return raw

    target_name = os.path.basename(raw)
    try:
        from modules.utils.obsidian_parser import find_day_file_by_date, list_day_files

        if task_date:
            target_dt = datetime.strptime(task_date, "%Y-%m-%d")
            dated_path = find_day_file_by_date(target_dt)
            if dated_path and os.path.basename(dated_path) == target_name:
                return dated_path

        for candidate in list_day_files():
            if os.path.basename(candidate) == target_name:
                return candidate
    except Exception:
        pass
    return raw


def _build_slot_reservations(schedule: list[dict[str, Any]]) -> dict[str, list[datetime]]:
    """채널별로 이미 점유된 예약 슬롯 목록을 만든다."""
    occupied: dict[str, list[datetime]] = {}
    for item in schedule:
        channel = str(item.get("channel") or "").strip()
        if not channel:
            continue
        publish_dt = item.get("publish_at")
        if not isinstance(publish_dt, datetime):
            publish_dt = _parse_publish_at_kst(str(item.get("publish_at_iso") or ""))
        if not publish_dt:
            continue
        occupied.setdefault(channel, []).append(publish_dt.astimezone(KST))
    for slots in occupied.values():
        slots.sort()
    return occupied


def _release_slot_reservation(occupied_slots: dict[str, list[datetime]], channel: str, publish_dt: datetime | None) -> None:
    """현재 아이템의 기존 슬롯을 점유 목록에서 제거."""
    if not publish_dt:
        return
    slots = occupied_slots.get(channel)
    if not slots:
        return
    for index, slot in enumerate(slots):
        if abs((slot - publish_dt.astimezone(KST)).total_seconds()) < 1:
            slots.pop(index)
            break


def _reserve_slot_reservation(occupied_slots: dict[str, list[datetime]], channel: str, publish_dt: datetime) -> None:
    """최종 확정된 슬롯을 점유 목록에 반영."""
    slots = occupied_slots.setdefault(channel, [])
    slots.append(publish_dt.astimezone(KST))
    slots.sort()


def _find_next_publish_slot(
    channel: str,
    min_publish_time: datetime,
    occupied_slots: dict[str, list[datetime]],
) -> datetime:
    """채널 윈도우/간격/일일 상한을 지키는 가장 이른 다음 슬롯을 찾는다."""
    window = CHANNEL_WINDOWS.get(channel)
    if not window:
        return min_publish_time

    min_interval = max(int(window.get("min_interval_min", 0)), 1)
    slot_step = 5
    channel_slots = occupied_slots.setdefault(channel, [])

    for day_offset in range(SLOT_SEARCH_DAYS):
        candidate_day = (min_publish_time + timedelta(days=day_offset)).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        window_start, window_end, _ = _get_window_bounds(candidate_day, window)
        capacity = _get_daily_capacity(window, candidate_day)
        day_slots = sorted(slot for slot in channel_slots if slot.date() == candidate_day.date())
        if len(day_slots) >= capacity:
            continue

        candidate = max(min_publish_time, window_start)
        candidate = _round_up_time(candidate, step_minutes=slot_step)
        while candidate <= window_end:
            conflicting = next(
                (slot for slot in day_slots if abs((slot - candidate).total_seconds()) < min_interval * 60),
                None,
            )
            if not conflicting:
                return candidate
            candidate = _round_up_time(
                max(candidate, conflicting + timedelta(minutes=min_interval)),
                step_minutes=slot_step,
            )

    return _round_up_time(min_publish_time + timedelta(days=1), step_minutes=10)


def _shift_past_slots_for_today(schedule: list[dict], target_date: datetime) -> list[dict]:
    """오늘 실행인데 이미 지난 예약 슬롯이 있으면 다음 채널 윈도우로 이월.

    수동 재실행 시 저녁에 몰아 넣지 않고, 채널별 일일 상한/간격을 그대로 지키며
    다음날 이후 예약으로 넘긴다.
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

    print(f"[자동 배포] 지난 예약 슬롯 {len(past_items)}개 감지 → 다음 채널 윈도우로 이월")
    base_date = target_kst.replace(hour=0, minute=0, second=0, microsecond=0)
    rescheduled: list[dict[str, Any]] = []

    future_offsets: dict[str, int] = {}
    for item in future_items:
        publish_dt = item["publish_at"]
        day_offset = max((publish_dt.date() - base_date.date()).days, 0)
        future_offsets[item["channel"]] = max(future_offsets.get(item["channel"], 0), day_offset)

    channels = sorted({item["channel"] for item in past_items})
    for channel in channels:
        channel_items = sorted(
            [item for item in past_items if item["channel"] == channel],
            key=lambda x: x.get("order", 0),
        )
        start_day_offset = future_offsets.get(channel, 0) + 1
        rescheduled.extend(
            _schedule_channel_items(
                channel,
                channel_items,
                base_date,
                start_day_offset=start_day_offset,
            )
        )

    merged = future_items + rescheduled
    merged.sort(key=lambda x: x["publish_at"])
    return merged


def _ensure_future_publish_at(
    publish_at_iso: str,
    channel: str,
    occupied_slots: dict[str, list[datetime]] | None = None,
) -> str:
    """업로드 직전에 예약 시간이 지났거나 충돌하면 다음 채널 윈도우 슬롯으로 재조정."""
    scheduled_dt = _parse_publish_at_kst(publish_at_iso)
    if not scheduled_dt:
        return publish_at_iso

    if occupied_slots is None:
        occupied_slots = {}
    now_kst = datetime.now(KST)
    min_publish_time = _round_up_time(now_kst + timedelta(minutes=UPLOAD_MIN_LEAD_MINUTES))
    adjusted_kst = scheduled_dt
    if adjusted_kst < min_publish_time:
        adjusted_kst = _find_next_publish_slot(channel, min_publish_time, occupied_slots)
    elif channel in CHANNEL_WINDOWS:
        adjusted_kst = _find_next_publish_slot(channel, adjusted_kst, occupied_slots)

    _reserve_slot_reservation(occupied_slots, channel, adjusted_kst)
    adjusted_utc = adjusted_kst.astimezone(timezone.utc)
    adjusted_iso = adjusted_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    if adjusted_kst != scheduled_dt:
        print(
            f"[자동 배포] 예약 시간 보정: {channel} "
            f"{scheduled_dt.strftime('%Y-%m-%d %H:%M KST')} → {adjusted_kst.strftime('%Y-%m-%d %H:%M KST')}"
        )
    return adjusted_iso


def _preflight_tts() -> bool:
    """TTS 서버 헬스체크 — 배치 시작 전 연결 확인."""
    import requests
    configured_url = os.getenv("QWEN3_TTS_URL", "").strip()
    candidates = [
        configured_url,
        "http://localhost:8010",
        "http://host.docker.internal:8010",
        "http://tts:8010",
    ]
    seen: set[str] = set()
    errors: list[str] = []
    for raw_url in candidates:
        tts_url = (raw_url or "").rstrip("/")
        if not tts_url or tts_url in seen:
            continue
        seen.add(tts_url)
        try:
            resp = requests.get(f"{tts_url}/health", timeout=5)
            if resp.status_code == 200:
                print(f"[사전 체크] TTS 서버 정상: {tts_url}")
                return True
            errors.append(f"{tts_url}/health -> {resp.status_code}")
        except Exception as exc:
            errors.append(f"{tts_url}/health -> {type(exc).__name__}")

        # /health 없으면 root 체크
        try:
            resp = requests.get(tts_url, timeout=5)
            if resp.status_code < 500:
                print(f"[사전 체크] TTS 서버 응답 확인: {tts_url}")
                return True
            errors.append(f"{tts_url} -> {resp.status_code}")
        except Exception as exc:
            errors.append(f"{tts_url} -> {type(exc).__name__}")

    print(f"[사전 체크] TTS 서버 연결 불가: {'; '.join(errors[-6:])}")
    return False


def _notify_batch_abort(reason: str):
    """배치 중단 알림 — Telegram."""
    try:
        from modules.utils.notify import _send
        _send(
            f"🛑 <b>배치 중단</b>\n{reason}\n⏰ {datetime.now(KST).strftime('%H:%M')}",
            kind="batch_abort",
            meta={"reason": reason},
        )
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


def _read_lock_file() -> dict[str, Any] | None:
    """현재 배포 락 파일 메타데이터를 읽는다."""
    try:
        if not os.path.exists(DEPLOY_LOCK_FILE):
            return None
        with open(DEPLOY_LOCK_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _acquire_deploy_lock(target_date_str: str) -> tuple[bool, str | None]:
    """배치 중복 실행 방지를 위한 프로세스 락 획득."""
    lock_dir = os.path.dirname(DEPLOY_LOCK_FILE) or "."
    os.makedirs(lock_dir, exist_ok=True)
    payload = {
        "pid": os.getpid(),
        "current_date": target_date_str,
        "created_at": datetime.now(KST).isoformat(),
    }
    try:
        fd = os.open(DEPLOY_LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        existing = _read_lock_file() or {}
        created_at = str(existing.get("created_at") or "")
        is_stale = False
        try:
            pid = int(existing.get("pid") or 0)
            if pid > 0 and os.name != "nt":
                os.kill(pid, 0)
        except Exception:
            is_stale = True
        if created_at:
            try:
                created_dt = datetime.fromisoformat(created_at)
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=KST)
                if (datetime.now(KST) - created_dt.astimezone(KST)).total_seconds() > DEPLOY_LOCK_TTL_SECONDS:
                    is_stale = True
            except Exception:
                is_stale = True
        if is_stale:
            try:
                os.unlink(DEPLOY_LOCK_FILE)
            except Exception:
                pass
            return _acquire_deploy_lock(target_date_str)
        owner = existing.get("pid") or "unknown"
        owner_date = existing.get("current_date") or "unknown"
        return False, f"이미 배포가 진행 중입니다 (pid={owner}, date={owner_date})"
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        try:
            os.unlink(DEPLOY_LOCK_FILE)
        except Exception:
            pass
        raise
    return True, None


def _release_deploy_lock() -> None:
    """현재 프로세스가 점유한 배포 락 해제."""
    payload = _read_lock_file() or {}
    if payload.get("pid") not in {None, os.getpid()}:
        return
    try:
        if os.path.exists(DEPLOY_LOCK_FILE):
            os.unlink(DEPLOY_LOCK_FILE)
    except Exception as e:
        print(f"[자동 배포] 락 해제 실패(무시): {e}")


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
                        topic_group = str(r.get("topic_group") or r.get("topic") or "").strip()
                        channel = str(r.get("channel") or "").strip()
                        if topic_group and channel:
                            completed.add(f"{channel}:{topic_group}")
                if completed:
                    print(f"[자동 배포] 이전 배포에서 {len(completed)}개 완료 토픽 발견 → 스킵")
                return completed
    except Exception as e:
        print(f"[자동 배포] 상태 로드 실패 (무시): {e}")
    return set()


def _read_state_file() -> dict[str, Any] | None:
    """마지막 저장된 배포 상태를 읽는다."""
    try:
        if not os.path.exists(STATE_FILE):
            return None
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception as e:
        print(f"[자동 배포] 상태 파일 읽기 실패(무시): {e}")
        return None


def _clean_youtube_url(value: str | None) -> str:
    """상태 문자열에서 실제 YouTube URL만 추출한다."""
    text = str(value or "").strip()
    match = re.search(r"https?://[^\s)]+", text)
    return match.group(0) if match else text


def _extract_youtube_video_id(value: str | None) -> str:
    """YouTube shorts/watch URL에서 video id를 추출한다."""
    url = _clean_youtube_url(value)
    if not url:
        return ""
    patterns = [
        r"youtube\.com/shorts/([A-Za-z0-9_-]+)",
        r"youtube\.com/watch\?v=([A-Za-z0-9_-]+)",
        r"youtu\.be/([A-Za-z0-9_-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return ""


def _get_rollout_threshold(channel: str, channel_avg_views: int) -> int:
    """Lead 채널이 holdback 확장을 열어줄 최소 조회수."""
    min_views = max(1, int(os.getenv("ROLLOUT_EXPANSION_MIN_VIEWS", "800")))
    avg_multiplier = max(0.1, float(os.getenv("ROLLOUT_EXPANSION_AVG_MULTIPLIER", "1.0")))
    return max(min_views, int(round(max(channel_avg_views, 0) * avg_multiplier)))


def _get_rollout_retention_threshold(channel_avg_retention: float) -> float:
    """Lead 채널이 holdback 확장을 열어줄 최소 완시율."""
    min_retention = max(1.0, float(os.getenv("ROLLOUT_EXPANSION_MIN_RETENTION", "32")))
    avg_ratio = max(0.1, float(os.getenv("ROLLOUT_EXPANSION_RETENTION_RATIO", "0.9")))
    if channel_avg_retention <= 0:
        return min_retention
    return max(min_retention, round(channel_avg_retention * avg_ratio, 1))


def _build_occupied_slots_from_task_history(from_dt: datetime | None = None) -> dict[str, list[datetime]]:
    """이미 예약된 publishAt 이력을 today_tasks DB에서 복원한다."""
    occupied: dict[str, list[datetime]] = {}
    try:
        from modules.utils.today_tasks import list_reserved_publish_slots

        from_iso = None
        if from_dt:
            from_iso = from_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for row in list_reserved_publish_slots(from_iso=from_iso):
            channel = str(row.get("channel") or "").strip()
            publish_at = _parse_publish_at_kst(str(row.get("publish_at") or ""))
            if not channel or not publish_at:
                continue
            occupied.setdefault(channel, []).append(publish_at)
        for slots in occupied.values():
            slots.sort()
    except Exception as exc:
        print(f"[롤아웃 큐] 예약 슬롯 복원 실패(무시): {exc}")
    return occupied


def _register_rollout_candidate(
    item: dict[str, Any],
    *,
    task_date: str,
    channel: str,
    publish_at: str,
    youtube_url: str | None,
) -> None:
    """Lead 채널 성공 시 holdback 확장 후보를 큐에 등록한다."""
    if item.get("rollout_strategy") != "lead_channel_first":
        return
    if str(item.get("lead_channel") or "").strip() != channel:
        return

    holdback_payload = item.get("holdback_channel_data") or {}
    if not isinstance(holdback_payload, dict) or not holdback_payload:
        return

    source_file = _resolve_source_file_path(
        str(item.get("source_file") or item.get("day_file") or "").strip() or None,
        task_date=task_date,
    )
    try:
        from modules.scheduler.rollout_queue import register_candidate

        register_candidate(
            lead_task_date=task_date,
            topic_group=str(item.get("topic_group") or item.get("topic") or "").strip(),
            lead_channel=channel,
            holdback_payload=holdback_payload,
            format_type=str(item.get("format_type") or "").strip() or None,
            series_title=str(item.get("series_title") or "").strip() or None,
            source_file=source_file,
            lead_publish_at=publish_at,
            lead_video_url=_clean_youtube_url(youtube_url),
        )
    except Exception as exc:
        print(f"[롤아웃 큐] 후보 등록 실패(무시): {exc}")


async def process_rollout_expansions(limit: int = 6) -> dict[str, Any]:
    """24시간 경과한 lead topic의 holdback 채널을 자동 확장한다."""
    from modules.scheduler.rollout_queue import (
        claim_due_candidates,
        get_queue_summary,
        mark_candidate_expanded,
        mark_candidate_skipped,
        release_candidate,
    )
    from modules.utils.today_tasks import get_completed_keys, upsert_task_status
    from modules.utils.youtube_stats import fetch_channel_stats, fetch_video_stats
    import httpx

    if _read_lock_file():
        return {
            "success": False,
            "message": "일반 자동 배포가 진행 중이라 rollout expansion을 잠시 미룹니다.",
            "queue": get_queue_summary(),
            "results": [],
        }

    now_kst = datetime.now(KST)
    candidates = claim_due_candidates(limit=limit, now=now_kst)
    if not candidates:
        return {"success": True, "processed": 0, "queue": get_queue_summary(), "results": []}

    lang_map = {"askanything": "ko", "wonderdrop": "en", "exploratodo": "es", "prismtale": "es"}
    channel_stats_cache: dict[str, dict[str, Any]] = {}
    retention_cache: dict[str, dict[str, Any]] = {}
    occupied_slots = _build_occupied_slots_from_task_history(now_kst - timedelta(minutes=5))
    api_port = os.getenv("API_PORT", "8003")
    results: list[dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0)) as client:
        for candidate in candidates:
            candidate_id = int(candidate.get("id") or 0)
            topic_group = str(candidate.get("topic_group") or "").strip()
            lead_channel = str(candidate.get("lead_channel") or "").strip()
            lead_task_date = str(candidate.get("lead_task_date") or "").strip()
            lead_video_url = _clean_youtube_url(candidate.get("lead_video_url"))
            holdback_payload = candidate.get("holdback_payload") or {}
            source_file = _resolve_source_file_path(candidate.get("source_file"), task_date=lead_task_date)
            lead_video_id = _extract_youtube_video_id(lead_video_url)

            if not topic_group or not lead_channel or not holdback_payload or not lead_video_id:
                release_candidate(candidate_id, last_error="lead 메타데이터가 부족해 다음 주기에 재시도합니다.")
                results.append({
                    "topic_group": topic_group,
                    "lead_channel": lead_channel,
                    "status": "deferred",
                    "reason": "missing_metadata",
                })
                continue

            stats_bundle = channel_stats_cache.get(lead_channel)
            if stats_bundle is None:
                stats_bundle = fetch_channel_stats(lead_channel, max_results=50)
                channel_stats_cache[lead_channel] = stats_bundle
            lead_stats = next(
                (video for video in stats_bundle.get("videos", []) if str(video.get("video_id") or "") == lead_video_id),
                None,
            )
            if not lead_stats:
                lead_stats = fetch_video_stats(lead_channel, lead_video_id)
            if not lead_stats:
                release_candidate(candidate_id, last_error="lead 영상 통계가 아직 보이지 않아 다음 주기에 재시도합니다.")
                results.append({
                    "topic_group": topic_group,
                    "lead_channel": lead_channel,
                    "status": "deferred",
                    "reason": "stats_not_ready",
                })
                continue

            views = int(lead_stats.get("views") or 0)
            channel_avg = int((stats_bundle.get("summary") or {}).get("avg_views") or 0)
            threshold = _get_rollout_threshold(lead_channel, channel_avg)
            if views < threshold:
                mark_candidate_skipped(
                    candidate_id,
                    metric_views=views,
                    threshold_views=threshold,
                    last_error=f"24h 조회수 {views} < 확장 기준 {threshold}",
                )
                results.append({
                    "topic_group": topic_group,
                    "lead_channel": lead_channel,
                    "status": "skipped",
                    "views": views,
                    "threshold": threshold,
                })
                continue

            retention_value: float | None = None
            retention_threshold: float | None = None
            try:
                from modules.analytics.youtube_analytics import fetch_retention_data, get_cached_retention

                retention_bundle = retention_cache.get(lead_channel)
                if retention_bundle is None:
                    retention_bundle = get_cached_retention(lead_channel) or {}
                    cached_videos = retention_bundle.get("videos") or []
                    if not any(str(video.get("video_id") or "") == lead_video_id for video in cached_videos):
                        fetched_bundle = fetch_retention_data(lead_channel, days=7)
                        if fetched_bundle.get("videos"):
                            retention_bundle = fetched_bundle
                    retention_cache[lead_channel] = retention_bundle

                if not retention_bundle.get("error"):
                    retention_video = next(
                        (
                            video for video in (retention_bundle.get("videos") or [])
                            if str(video.get("video_id") or "") == lead_video_id
                        ),
                        None,
                    )
                    if retention_video:
                        retention_value = float(retention_video.get("avg_view_percentage") or 0)
                        retention_threshold = _get_rollout_retention_threshold(
                            float(retention_bundle.get("channel_avg_retention") or 0)
                        )
            except Exception as retention_exc:
                print(f"[롤아웃 큐] 완시율 게이트 조회 실패(무시): {retention_exc}")

            retention_required = os.getenv("ROLLOUT_REQUIRE_RETENTION", "false").lower() in {"1", "true", "yes", "on"}
            if retention_required and retention_value is None:
                release_candidate(candidate_id, last_error="완시율 데이터가 아직 없어 다음 주기에 재시도합니다.")
                results.append({
                    "topic_group": topic_group,
                    "lead_channel": lead_channel,
                    "status": "deferred",
                    "reason": "retention_not_ready",
                    "views": views,
                    "threshold": threshold,
                })
                continue

            if retention_value is not None and retention_threshold is not None and retention_value < retention_threshold:
                mark_candidate_skipped(
                    candidate_id,
                    metric_views=views,
                    threshold_views=threshold,
                    last_error=f"24h 완시율 {retention_value:.1f}% < 확장 기준 {retention_threshold:.1f}%",
                )
                results.append({
                    "topic_group": topic_group,
                    "lead_channel": lead_channel,
                    "status": "skipped_retention",
                    "views": views,
                    "threshold": threshold,
                    "retention": retention_value,
                    "retention_threshold": retention_threshold,
                })
                continue

            completed_keys = get_completed_keys(lead_task_date)
            min_publish_time = _round_up_time(now_kst + timedelta(minutes=UPLOAD_MIN_LEAD_MINUTES))
            successes = 0
            failures = 0
            channel_results: list[dict[str, Any]] = []

            for channel, channel_data in holdback_payload.items():
                channel = str(channel or "").strip()
                if not channel:
                    continue
                if f"{topic_group}::{channel}" in completed_keys:
                    successes += 1
                    channel_results.append({
                        "channel": channel,
                        "status": "skipped_completed",
                        "source_topic": str(
                            (
                                channel_data.get("source_topic")
                                if isinstance(channel_data, dict)
                                else ""
                            )
                            or (
                                channel_data.get("_llm_topic_override")
                                if isinstance(channel_data, dict)
                                else ""
                            )
                            or (
                                channel_data.get("title")
                                if isinstance(channel_data, dict)
                                else ""
                            )
                            or topic_group
                        ).strip(),
                    })
                    continue

                publish_dt = _find_next_publish_slot(channel, min_publish_time, occupied_slots)
                _reserve_slot_reservation(occupied_slots, channel, publish_dt)
                publish_at = publish_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                title = ""
                source_topic = ""
                if isinstance(channel_data, dict):
                    title = str(channel_data.get("title") or "").strip()
                    source_topic = str(
                        channel_data.get("source_topic")
                        or channel_data.get("_llm_topic_override")
                        or ""
                    ).strip()
                llm_topic = source_topic or title or topic_group

                try:
                    flow_result = await _prepare_render_upload_via_preview_flow(
                        client=client,
                        api_port=api_port,
                        topic=llm_topic,
                        language=lang_map.get(channel, "ko"),
                        channel=channel,
                        format_type=str(candidate.get("format_type") or "").strip() or None,
                        publish_at=publish_at,
                        series_title=str(candidate.get("series_title") or "").strip() or None,
                        task_date=lead_task_date,
                        topic_group=topic_group,
                    )
                    upsert_task_status(
                        task_date=lead_task_date,
                        topic_group=topic_group,
                        channel=channel,
                        title=flow_result.get("title") or topic_group,
                        source_topic=llm_topic,
                        status="completed",
                        source="rollout_expansion",
                        source_file=source_file,
                        video_path=flow_result.get("video_path", ""),
                        youtube_url=_clean_youtube_url(flow_result.get("youtube_url")),
                        publish_at=flow_result.get("publish_at", publish_at),
                    )
                    successes += 1
                    channel_results.append({
                        "channel": channel,
                        "status": "success",
                        "source_topic": llm_topic,
                        "youtube_url": _clean_youtube_url(flow_result.get("youtube_url")),
                        "publish_at": flow_result.get("publish_at", publish_at),
                    })
                except Exception as exc:
                    failures += 1
                    channel_results.append({
                        "channel": channel,
                        "status": "failed",
                        "source_topic": llm_topic,
                        "error": str(exc)[:200],
                    })
                    upsert_task_status(
                        task_date=lead_task_date,
                        topic_group=topic_group,
                        channel=channel,
                        title=title or topic_group,
                        source_topic=llm_topic,
                        status="failed",
                        source="rollout_expansion",
                        note=str(exc)[:200],
                        source_file=source_file,
                        publish_at=publish_at,
                    )

            if failures == 0:
                mark_candidate_expanded(
                    candidate_id,
                    metric_views=views,
                    threshold_views=threshold,
                    expanded_task_date=now_kst.strftime("%Y-%m-%d"),
                )
                if source_file:
                    try:
                        from modules.utils.obsidian_parser import tick_topic_done

                        tick_topic_done(source_file, topic_group)
                    except Exception:
                        pass
            else:
                release_candidate(
                    candidate_id,
                    last_error=f"holdback {failures}건 실패 — 다음 주기에 남은 채널 재시도",
                )

            results.append({
                "topic_group": topic_group,
                "lead_channel": lead_channel,
                "status": "expanded" if failures == 0 else "partial_retry",
                "views": views,
                "threshold": threshold,
                "retention": retention_value,
                "retention_threshold": retention_threshold,
                "channels": channel_results,
            })

    return {
        "success": True,
        "processed": len(candidates),
        "queue": get_queue_summary(),
        "results": results,
    }


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
    task_date: str | None = None,
    topic_group: str | None = None,
    video_engine_override: str | None = None,
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

    video_engine = str(video_engine_override or os.getenv("AUTO_DEPLOY_VIDEO_ENGINE", "veo3")).strip().lower() or "veo3"
    video_model = "hero-only" if video_engine == "veo3" else None
    render_payload = {
        "sessionId": session_id,
        "cuts": [{"index": c.get("index", i), "script": c.get("script", "")} for i, c in enumerate(cuts)],
        "videoEngine": video_engine,
        "videoModel": video_model,
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
    tags = [str(t).lstrip("#").strip() for t in (preview_data.get("tags") or []) if str(t).strip()][:5]

    from modules.upload.youtube.upload import _prepare_youtube_metadata
    from modules.upload.youtube import upload_video as yt_upload
    from modules.utils.channel_config import get_upload_account

    description, tags = _prepare_youtube_metadata(description, tags)

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
            task_date=task_date,
            topic_group=topic_group,
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
    def _build_runtime_summary(task_date: str | None, results: list[dict[str, Any]]) -> dict[str, Any]:
        success_counts: dict[str, int] = {}
        publish_on_date: dict[str, int] = {}
        carryover_next_days: dict[str, int] = {}
        publish_dates: dict[str, dict[str, int]] = {}

        for item in results:
            if item.get("status") != "success":
                continue
            channel = str(item.get("channel") or "").strip()
            if not channel:
                continue
            success_counts[channel] = success_counts.get(channel, 0) + 1
            publish_dt = _parse_publish_at_kst(str(item.get("publish_at") or ""))
            if not publish_dt or not task_date:
                continue
            publish_day = publish_dt.astimezone(KST).strftime("%Y-%m-%d")
            bucket = publish_dates.setdefault(publish_day, {})
            bucket[channel] = bucket.get(channel, 0) + 1
            if publish_day == task_date:
                publish_on_date[channel] = publish_on_date.get(channel, 0) + 1
            elif publish_day > task_date:
                carryover_next_days[channel] = carryover_next_days.get(channel, 0) + 1

        rollout_items: list[dict[str, Any]] = []
        rollout_pending: dict[str, int] = {}
        pending_topics = 0
        try:
            from modules.scheduler.rollout_queue import list_candidates

            for candidate in list_candidates(limit=200):
                if str(candidate.get("lead_task_date") or "") != str(task_date or ""):
                    continue
                payload = candidate.get("holdback_payload") or {}
                holdback_channels = [
                    str(channel).strip()
                    for channel in payload.keys()
                    if str(channel).strip()
                ]
                source_topics = {}
                for channel, channel_data in payload.items():
                    if not isinstance(channel_data, dict):
                        continue
                    label = str(
                        channel_data.get("source_topic")
                        or channel_data.get("_llm_topic_override")
                        or channel_data.get("title")
                        or ""
                    ).strip()
                    if label:
                        source_topics[str(channel)] = label
                status = str(candidate.get("status") or "").strip() or "pending"
                rollout_items.append({
                    "id": candidate.get("id"),
                    "topic_group": candidate.get("topic_group"),
                    "lead_channel": candidate.get("lead_channel"),
                    "holdback_channels": holdback_channels,
                    "source_topics": source_topics,
                    "status": status,
                    "expand_after": candidate.get("expand_after"),
                    "lead_publish_at": candidate.get("lead_publish_at"),
                    "lead_video_url": candidate.get("lead_video_url"),
                    "format_type": candidate.get("format_type"),
                    "metric_views": candidate.get("metric_views"),
                    "threshold_views": candidate.get("threshold_views"),
                    "last_error": candidate.get("last_error"),
                })
                if status in {"pending", "processing"}:
                    pending_topics += 1
                    for channel in holdback_channels:
                        rollout_pending[channel] = rollout_pending.get(channel, 0) + 1
        except Exception as exc:
            print(f"[자동 배포] rollout 상태 요약 실패(무시): {exc}")

        channel_order = list(CHANNEL_WINDOWS.keys())
        for counts in (success_counts, publish_on_date, carryover_next_days, rollout_pending):
            for channel in counts:
                if channel not in channel_order:
                    channel_order.append(channel)

        def _ordered(counts: dict[str, int]) -> dict[str, int]:
            return {channel: int(counts.get(channel, 0) or 0) for channel in channel_order if channel in counts or counts.get(channel, 0)}

        final_expected = {
            channel: int(success_counts.get(channel, 0) or 0) + int(rollout_pending.get(channel, 0) or 0)
            for channel in channel_order
            if success_counts.get(channel, 0) or rollout_pending.get(channel, 0)
        }

        ordered_publish_dates = {
            day: {
                channel: int(counts.get(channel, 0) or 0)
                for channel in channel_order
                if counts.get(channel, 0)
            }
            for day, counts in sorted(publish_dates.items())
        }

        return {
            "channel_summary": {
                "completed": _ordered(success_counts),
                "rollout_pending": _ordered(rollout_pending),
                "final_expected": _ordered(final_expected),
                "publish_on_date": _ordered(publish_on_date),
                "carryover_next_days": _ordered(carryover_next_days),
            },
            "publish_dates": ordered_publish_dates,
            "rollout_overview": {
                "pending_topics": pending_topics,
                "pending_channels": sum(rollout_pending.values()),
                "items": rollout_items,
            },
        }

    current = {**_deploy_status}
    snapshot = current
    if not current.get("running"):
        saved = _read_state_file()
        if saved and (saved.get("running") or saved.get("total") or saved.get("results")):
            snapshot = {**current, **saved}
    if snapshot.get("running"):
        if not current.get("running"):
            snapshot["running"] = False
            snapshot["current_task"] = None
            snapshot["finished_at"] = snapshot.get("finished_at") or datetime.now(KST).isoformat()
            snapshot["stale_recovered"] = True
            snapshot["message"] = "이전 서버에서 진행 중이던 배치 상태를 복구했습니다."
    snapshot.update(_build_runtime_summary(snapshot.get("current_date"), snapshot.get("results") or []))
    return snapshot


def preview_schedule(target_date: datetime | None = None) -> dict[str, Any]:
    """스케줄 미리보기 — 영상 생성 없이 시간 배정만 확인."""
    from modules.utils.obsidian_parser import get_today_topics
    from modules.scheduler.topic_generator import find_day_file_topic_conflicts

    if target_date is None:
        target_date = datetime.now(KST)

    result = get_today_topics(target_date=target_date)
    if not result.get("file") or not result.get("topics"):
        return {
            "success": False,
            "message": f"{target_date.strftime('%m-%d')} Day 파일 없음",
        }
    day_file_path = result.get("file_path")
    if day_file_path:
        conflicts = find_day_file_topic_conflicts(day_file_path)
        if conflicts:
            return {
                "success": False,
                "file": result.get("file"),
                "message": "Day 파일 주제가 다른 날짜와 겹쳐 스케줄 미리보기를 중단했습니다.",
                "errors": conflicts,
            }

    base_schedule = calculate_schedule(result["topics"], target_date)
    adjusted_schedule = _shift_past_slots_for_today(base_schedule, target_date)
    return _build_schedule_response(
        file_name=result["file"],
        topics=result["topics"],
        schedule=adjusted_schedule,
        target_date=target_date,
    )


async def run_auto_deploy(target_date: datetime | None = None,
                          dry_run: bool = False,
                          max_per_channel: int | None = None,
                          video_engine: str | None = None) -> dict[str, Any]:
    """자동 배포 실행 — Day 파일 → 영상 생성 → 예약 업로드.

    Args:
        target_date: 배포 날짜 (None이면 오늘)
        dry_run: True면 스케줄만 계산하고 실제 생성/업로드 안 함
        max_per_channel: 채널당 최대 업로드 수 (None이면 전부)

    Returns:
        배포 결과 요약
    """
    global _deploy_status

    from modules.utils.obsidian_parser import get_today_topics
    from modules.scheduler.topic_generator import find_day_file_topic_conflicts

    if target_date is None:
        target_date = datetime.now(KST)
    date_str = target_date.strftime("%Y-%m-%d")

    lock_acquired = False
    should_notify_summary = False
    if not dry_run:
        lock_acquired, lock_error = _acquire_deploy_lock(date_str)
        if not lock_acquired:
            return {"success": False, "message": lock_error or "이미 배포가 진행 중입니다"}
        _deploy_status = {
            "running": True,
            "current_date": date_str,
            "total": 0,
            "completed": 0,
            "failed": 0,
            "current_task": None,
            "results": [],
            "started_at": datetime.now(KST).isoformat(),
            "finished_at": None,
        }

    try:
        # 1. Day 파일 파싱
        result = get_today_topics(target_date=target_date)
        if not result.get("file") or not result.get("topics"):
            return {
                "success": False,
                "message": f"{target_date.strftime('%m-%d')} Day 파일 없음",
            }

        day_file_path: str | None = result.get("file_path")
        if day_file_path:
            conflicts = find_day_file_topic_conflicts(day_file_path)
            if conflicts:
                return {
                    "success": False,
                    "file": result.get("file"),
                    "message": "Day 파일 주제가 다른 날짜와 겹쳐 자동 배포를 중단했습니다.",
                    "errors": conflicts,
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

        schedule = _shift_past_slots_for_today(schedule, target_date)

        if dry_run:
            payload = _build_schedule_response(
                file_name=result["file"],
                topics=result["topics"],
                schedule=schedule,
                target_date=target_date,
            )
            payload["dry_run"] = True
            return payload

        # 3. 사전 헬스체크 — TTS 서버 연결 확인
        tts_ok = _preflight_tts()
        if not tts_ok:
            _deploy_status.update({
                "total": len(schedule),
                "finished_at": datetime.now(KST).isoformat(),
            })
            _save_state()
            _notify_batch_abort("TTS 서버(Qwen3) 연결 불가 — 배치 중단")
            return {"success": False, "message": "TTS 서버 연결 불가. Docker 확인 필요."}

        # 4. 주제별 그룹핑 — 같은 주제의 채널들을 연속 처리
        schedule = _reorder_by_topic_group(schedule)

        # 5. 배포 시작 — 이전 완료 토픽 로드
        completed_keys = _load_state(date_str)
        try:
            from modules.utils.today_tasks import get_completed_keys as _get_today_completed_keys

            for task_key in _get_today_completed_keys(date_str):
                if "::" not in task_key:
                    continue
                topic_group, channel_name = task_key.split("::", 1)
                if topic_group and channel_name:
                    completed_keys.add(f"{channel_name}:{topic_group}")
        except Exception as completed_db_exc:
            print(f"[자동 배포] 오늘할일 완료 DB 병합 실패(무시): {completed_db_exc}")

        _prev_results = []
        try:
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    prev = json.load(f)
                if prev.get("current_date") == date_str:
                    _prev_results = [r for r in prev.get("results", []) if r.get("status") == "success"]
        except Exception:
            pass

        _deploy_status.update({
            "running": True,
            "current_date": date_str,
            "total": len(schedule),
            "completed": len(completed_keys),
            "failed": 0,
            "current_task": None,
            "results": _prev_results,
            "started_at": _deploy_status.get("started_at") or datetime.now(KST).isoformat(),
            "finished_at": None,
        })
        _save_state()

        should_notify_summary = True
        occupied_slots = _build_slot_reservations(schedule)
        consecutive_tts_fails = 0  # TTS 연속 실패 카운터

        for item in schedule:
            # 중복 방지: 이전 배포에서 성공한 토픽 스킵
            item_key = f"{item['channel']}:{item.get('topic_group') or item['topic']}"
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
                "source_topic": str(item.get("_llm_topic_override") or item.get("title") or topic).strip(),
                "status": "pending",
                "error": None,
                "video_path": None,
            }
            task_result["_retries"] = item.get("_retries", 0)

            original_publish_dt = item.get("publish_at") if isinstance(item.get("publish_at"), datetime) else _parse_publish_at_kst(publish_at)
            _release_slot_reservation(occupied_slots, channel, original_publish_dt)
            publish_at = _ensure_future_publish_at(publish_at, channel, occupied_slots)
            adjusted_publish_dt = _parse_publish_at_kst(publish_at)
            if adjusted_publish_dt:
                item["publish_at"] = adjusted_publish_dt
                item["publish_at_iso"] = publish_at
                item["publish_at_kst"] = adjusted_publish_dt.strftime("%Y-%m-%d %H:%M KST")
                task_result["publish_at"] = publish_at

            try:
                # 웹 미리보기 경로와 동일한 파이프라인 사용:
                # prepare(기획+이미지 세션) → render(TTS+Veo+Remotion) → upload(예약)
                import httpx

                lang_map = {"askanything": "ko", "wonderdrop": "en", "exploratodo": "es", "prismtale": "es"}
                lang = lang_map.get(channel, "ko")

                _item_title = item.get("title", "")
                _source_section = str(item.get("source_section") or "").strip()
                _topic_for_llm = str(item.get("_llm_topic_override") or "").strip()
                if not _topic_for_llm:
                    prefer_channel_title = bool(
                        _item_title
                        and _item_title != topic
                        and (lang != "ko" or _source_section == "Topic 3")
                    )
                    _topic_for_llm = _item_title if prefer_channel_title else topic
                task_result["source_topic"] = _topic_for_llm

                # 포맷 3단계 폴백: Day명시 → 키워드감지 → 채널선호
                _fmt = job.get("format_type")
                _raw_fmt = _fmt
                _fmt_src = "Day명시" if _fmt else None
                if not _fmt:
                    from modules.gpt.prompts.formats import detect_format_type
                    _fmt = detect_format_type(topic, lang)
                    _raw_fmt = _fmt
                    if _fmt:
                        _fmt_src = "키워드"
                if not _fmt:
                    from modules.utils.channel_config import get_channel_preset as _gcp
                    _preferred = (_gcp(channel) or {}).get("preferred_formats", [])
                    if _preferred:
                        import random as _random
                        _fmt = _random.choice(_preferred)
                        _fmt_src = "채널선호"
                _fmt, _fmt_guard = _normalize_format_for_channel(channel, _fmt)
                if _fmt_guard:
                    _fmt_src = f"{_fmt_src or '채널선호'}+가드"
                    print(f"  [포맷 가드] {_fmt_guard}")
                if _fmt != "COUNTDOWN" and (_raw_fmt == "COUNTDOWN" or _COUNTDOWN_CUE_PATTERN.search(_topic_for_llm)):
                    normalized_topic = _strip_countdown_cues(_topic_for_llm)
                    if normalized_topic and normalized_topic != _topic_for_llm:
                        print(f"  [토픽 가드] COUNTDOWN 신호 제거 → {normalized_topic}")
                        _topic_for_llm = normalized_topic
                if _fmt != "WHO_WINS" and _raw_fmt == "WHO_WINS":
                    normalized_topic = _soften_who_wins_cues(_topic_for_llm, lang)
                    if normalized_topic and normalized_topic != _topic_for_llm:
                        print(f"  [토픽 가드] WHO_WINS 신호 완화 → {normalized_topic}")
                        _topic_for_llm = normalized_topic
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
                        task_date=date_str,
                        topic_group=job.get("topic_group") or topic,
                        video_engine_override=video_engine,
                    )

                task_result["status"] = "success"
                consecutive_tts_fails = 0
                task_result["publish_at"] = flow_result.get("publish_at", publish_at)
                task_result["video_path"] = flow_result.get("video_path", "")
                task_result["youtube"] = {"url": _clean_youtube_url(flow_result.get("youtube_url", ""))}
                task_result["format_type"] = _fmt or job.get("format_type", "FACT")
                task_result["cut_count"] = flow_result.get("cut_count")
                try:
                    from modules.utils.today_tasks import upsert_task_status

                    upsert_task_status(
                        task_date=date_str,
                        topic_group=job.get("topic_group") or topic,
                        channel=channel,
                        title=flow_result.get("title") or topic,
                        source_topic=_topic_for_llm,
                        status="completed",
                        source="auto_deploy",
                        source_file=job.get("source_file") or job.get("day_file"),
                        video_path=flow_result.get("video_path", ""),
                        youtube_url=_clean_youtube_url(flow_result.get("youtube_url", "")),
                        publish_at=flow_result.get("publish_at", publish_at),
                    )
                except Exception as task_db_exc:
                    print(f"  [오늘할일 DB] 완료 기록 실패(무시): {task_db_exc}")
                _register_rollout_candidate(
                    item,
                    task_date=date_str,
                    channel=channel,
                    publish_at=flow_result.get("publish_at", publish_at),
                    youtube_url=flow_result.get("youtube_url", ""),
                )
                try:
                    from modules.utils.cost_tracker import calc_llm_cost, record_generation_cost

                    _cut_count = int(flow_result.get("cut_count") or 0)
                    _llm_model = os.getenv("TOPIC_LLM_MODEL") or os.getenv("LLM_MODEL") or "gemini-2.5-pro"
                    _est_input = 15000 + _cut_count * 500
                    _est_output = _cut_count * 500

                    record_generation_cost(
                        channel=channel,
                        success=True,
                        llm_usd=calc_llm_cost(_llm_model, _est_input, _est_output),
                        video_model=os.getenv("VEO_MODEL") or "hero-only",
                    )
                except Exception as cost_exc:
                    print(f"  [비용 추적] 기록 실패(무시): {cost_exc}")
                _deploy_status["completed"] += 1
                _deploy_status["results"].append(task_result)
                _save_state()
                _display_title = flow_result.get("title") or topic
                print(f"  ✅ 완료: {channel} — '{_display_title}'")
                # Day 파일 체크박스
                if day_file_path:
                    topic_group = job.get("topic_group", "")
                    if topic_group:
                        rollout_pending = bool(item.get("rollout_strategy") == "lead_channel_first" and item.get("holdback_channels"))
                        group_total = sum(1 for s in schedule if s.get("topic_group") == topic_group)
                        group_success = sum(1 for r in _deploy_status["results"] if r.get("topic_group") == topic_group and r.get("status") == "success")
                        if not rollout_pending and group_success >= group_total:
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
                        video_engine="veo3",
                        video_model="hero-only",
                    )
                except Exception:
                    pass

            except Exception as e:
                err_str = str(e)[:200]
                is_retryable = any(k in err_str.lower() for k in ["429", "timeout", "resource_exhausted", "rate limit", "connection"])
                is_hard_fail = "[hard fail]" in err_str.lower()

                if is_retryable and task_result.get("_retries", 0) < 2:
                    retry_num = task_result.get("_retries", 0) + 1
                    wait_sec = 30 * (2 ** (retry_num - 1))
                    print(f"  ⏳ 리트라이 — {wait_sec}초 후 재시도 ({retry_num}/2): {err_str}")
                    await asyncio.sleep(wait_sec)
                    task_result["_retries"] = retry_num
                    schedule.append({**item, "_retries": retry_num})
                    continue

                if is_hard_fail and not item.get("_hard_fail_retried"):
                    retry_topic = _pick_retry_topic_for_hard_fail(item, topic, lang)
                    if retry_topic:
                        print(f"  🔁 HARD FAIL 재시도 — 채널 제목 기준으로 1회 재생성: {retry_topic}")
                        await asyncio.sleep(5)
                        schedule.append({
                            **item,
                            "_hard_fail_retried": True,
                            "_llm_topic_override": retry_topic,
                        })
                        continue

                task_result["status"] = "failed"
                task_result["source_topic"] = str(job.get("_llm_topic_override") or job.get("title") or topic).strip()
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
                    notify_failure(
                        channel,
                        topic,
                        error=err_str,
                        video_engine="veo3",
                        video_model="hero-only",
                    )
                except Exception:
                    pass

            if task_result.get("status") != "success":
                try:
                    from modules.utils.today_tasks import upsert_task_status

                    upsert_task_status(
                        task_date=date_str,
                        topic_group=job.get("topic_group") or task_result.get("topic") or "",
                        channel=task_result.get("channel") or "",
                        title=task_result.get("topic") or "",
                        source_topic=task_result.get("source_topic") or "",
                        status="failed",
                        source="auto_deploy",
                        note=task_result.get("error"),
                        source_file=job.get("source_file") or job.get("day_file"),
                        publish_at=task_result.get("publish_at") or publish_at,
                    )
                except Exception as task_db_exc:
                    print(f"  [오늘할일 DB] 실패 기록 실패(무시): {task_db_exc}")
                _deploy_status["results"].append(task_result)
            _save_state()

    finally:
        if not dry_run and lock_acquired:
            _deploy_status["running"] = False
            _deploy_status["current_task"] = None
            _deploy_status["finished_at"] = datetime.now(KST).isoformat()
            _save_state()  # 최종 상태 저장
            if should_notify_summary:
                try:
                    from modules.utils.notify import notify_deploy_summary
                    notify_deploy_summary(
                        _deploy_status["total"], _deploy_status["completed"],
                        _deploy_status["failed"], date_str,
                    )
                except Exception:
                    pass
            _release_deploy_lock()

    return {
        "success": True,
        "total": _deploy_status["total"],
        "completed": _deploy_status["completed"],
        "failed": _deploy_status["failed"],
        "results": _deploy_status["results"],
    }
