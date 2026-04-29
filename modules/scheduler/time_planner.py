"""채널별 업로드 시간 자동 분배 — Day 파일 기반 스케줄링.

Day 파일 → 채널별 영상 수 계산 → 시간 윈도우 내 균등 분배 → publishAt 생성
필요 시 채널별 하루 업로드 상한을 적용하고 초과분은 다음날로 자동 이월한다.
"""
import os
import copy
from datetime import datetime, timedelta, timezone, time as dt_time
from typing import Any

from modules.utils.channel_config import pick_lead_channel

# KST 타임존
KST = timezone(timedelta(hours=9))

# 채널별 최적 업로드 시간 윈도우 (KST 기준)
# ※ 이 시간은 YouTube publishAt (예약 공개 시간) — 시청자 피크에 맞춤
# ※ 배치(영상 생성)는 새벽 2~6시에 별도 실행, 여기서는 공개 시간만 제어
CHANNEL_WINDOWS = {
    "askanything": {
        "start": dt_time(19, 30),  # KST 19:30 — 한국 저녁 프라임 초입부터 선점
        "end": dt_time(22, 0),     # KST 22:00
        "min_interval_min": 60,
        "daily_cap": 3,
    },
    "wonderdrop": {
        "start": dt_time(8, 0),    # KST 08:00 = EST 19:00 — 미국 저녁 프라임
        "end": dt_time(10, 30),    # KST 10:30 = EST 21:30 — Exploratodo와 겹침 축소
        "min_interval_min": 60,
        "daily_cap": 3,
    },
    "exploratodo": {
        "start": dt_time(11, 0),   # KST 11:00 = CST 21:00 — Wonderdrop/PrismTale와 분리
        "end": dt_time(13, 30),    # KST 13:30 = CST 23:30
        "min_interval_min": 75,
        "daily_cap": 3,
    },
    "prismtale": {
        "start": dt_time(7, 30),   # KST 07:30 = EST 18:30 / CET 00:30 — US 저녁 우선
        "end": dt_time(9, 30),     # KST 09:30 = EST 20:30 — ExploraTodo와 최소 90분 분리
        "min_interval_min": 75,
        "daily_cap": 2,            # 최근 자기잠식 방지: PrismTale은 하루 2개 상한
    },
}

LEAD_CHANNEL_FIRST_ENABLED = os.getenv("LEAD_CHANNEL_FIRST_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
LEAD_CHANNEL_FIRST_GROUPS_PER_DAY = max(0, int(os.getenv("LEAD_CHANNEL_FIRST_GROUPS_PER_DAY", "0")))


def _get_window_bounds(base_date: datetime, window: dict[str, Any]) -> tuple[datetime, datetime, float]:
    """채널 윈도우의 시작/끝 datetime과 총 분 수를 반환."""
    start_dt = base_date.replace(hour=window["start"].hour, minute=window["start"].minute, tzinfo=KST)
    end_dt = base_date.replace(hour=window["end"].hour, minute=window["end"].minute, tzinfo=KST)
    window_minutes = max((end_dt - start_dt).total_seconds() / 60, 0)
    return start_dt, end_dt, window_minutes


def _get_daily_capacity(window: dict[str, Any], base_date: datetime) -> int:
    """윈도우 길이와 최소 간격을 함께 고려한 실제 하루 배치 가능 수."""
    _, _, window_minutes = _get_window_bounds(base_date, window)
    min_interval = max(int(window.get("min_interval_min", 0)), 1)
    max_items_by_window = max(1, int(window_minutes // min_interval) + 1)
    configured_cap = int(window.get("daily_cap") or max_items_by_window)
    return max(1, min(configured_cap, max_items_by_window))


def _schedule_channel_items(
    channel: str,
    items: list[dict[str, Any]],
    base_date: datetime,
    *,
    start_day_offset: int = 0,
) -> list[dict[str, Any]]:
    """단일 채널 아이템에 예약 시간을 배정한다."""
    window = CHANNEL_WINDOWS.get(channel)
    if not window or not items:
        return []

    daily_cap = _get_daily_capacity(window, base_date)
    scheduled: list[dict[str, Any]] = []

    for day_index, chunk_start in enumerate(range(0, len(items), daily_cap)):
        day_items = items[chunk_start:chunk_start + daily_cap]
        chunk_date = base_date + timedelta(days=start_day_offset + day_index)
        start_dt, _, window_minutes = _get_window_bounds(chunk_date, window)
        n = len(day_items)
        if n == 1:
            interval_min = 0
        else:
            interval_min = max(
                int(window.get("min_interval_min", 0)),
                window_minutes / max(n - 1, 1),
            )

        for slot_index, topic_item in enumerate(day_items):
            topic_name = topic_item["topic"] if isinstance(topic_item, dict) else topic_item
            topic_title = topic_item.get("title", topic_name) if isinstance(topic_item, dict) else topic_name
            publish_time = start_dt + timedelta(minutes=interval_min * slot_index)
            publish_utc = publish_time.astimezone(timezone.utc)
            global_index = chunk_start + slot_index

            scheduled.append({
                "topic": topic_name,
                "title": topic_title,
                "channel": channel,
                "topic_group": topic_item.get("topic_group", topic_name) if isinstance(topic_item, dict) else topic_name,
                "format_type": topic_item.get("format_type", "FACT") if isinstance(topic_item, dict) else "FACT",
                "_llm_topic_override": topic_item.get("_llm_topic_override") if isinstance(topic_item, dict) else None,
                "split_mode": topic_item.get("split_mode") if isinstance(topic_item, dict) else None,
                "series_title": topic_item.get("series_title") if isinstance(topic_item, dict) else None,
                "source_file": (topic_item.get("source_file") or topic_item.get("day_file")) if isinstance(topic_item, dict) else None,
                "day_file": (topic_item.get("day_file") or topic_item.get("source_file")) if isinstance(topic_item, dict) else None,
                "source_section": topic_item.get("source_section") if isinstance(topic_item, dict) else None,
                "rollout_strategy": topic_item.get("rollout_strategy") if isinstance(topic_item, dict) else None,
                "lead_channel": topic_item.get("lead_channel") if isinstance(topic_item, dict) else None,
                "holdback_channels": topic_item.get("holdback_channels", []) if isinstance(topic_item, dict) else [],
                "holdback_channel_data": topic_item.get("holdback_channel_data", {}) if isinstance(topic_item, dict) else {},
                "publish_at_kst": publish_time.strftime("%Y-%m-%d %H:%M KST"),
                "publish_at_iso": publish_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "publish_at": publish_time,
                "order": global_index,
                "day_offset": start_day_offset + day_index,
            })

    return scheduled


def _apply_lead_channel_first(topics: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """하루 1개 공통 토픽을 선행 채널 1곳만 먼저 배포하도록 축소한다."""
    if not LEAD_CHANNEL_FIRST_ENABLED or LEAD_CHANNEL_FIRST_GROUPS_PER_DAY <= 0:
        return topics, []

    remaining = LEAD_CHANNEL_FIRST_GROUPS_PER_DAY
    transformed: list[dict[str, Any]] = []
    rollout_notes: list[dict[str, Any]] = []

    for topic in topics:
        channels = topic.get("channels", {}) or {}
        if (
            remaining > 0
            and topic.get("topic_tag") == "공통"
            and topic.get("split_mode") != "channel_specific"
            and isinstance(channels, dict)
            and len(channels) >= 2
        ):
            lead_channel = pick_lead_channel(topic.get("format_type"), channels.keys())
            if lead_channel and lead_channel in channels:
                lead_topic = copy.deepcopy(topic)
                lead_topic["channels"] = {
                    lead_channel: copy.deepcopy(channels[lead_channel]),
                }
                holdbacks = [channel for channel in channels.keys() if channel != lead_channel]
                lead_topic["rollout_strategy"] = "lead_channel_first"
                lead_topic["lead_channel"] = lead_channel
                lead_topic["holdback_channels"] = holdbacks
                lead_topic["holdback_channel_data"] = {
                    channel: copy.deepcopy(channels[channel])
                    for channel in holdbacks
                    if channel in channels
                }
                transformed.append(lead_topic)
                rollout_notes.append({
                    "topic_group": topic.get("topic_group"),
                    "format_type": topic.get("format_type", "FACT"),
                    "lead_channel": lead_channel,
                    "holdback_channels": holdbacks,
                })
                remaining -= 1
                continue

        transformed.append(topic)

    return transformed, rollout_notes


def count_scheduled_videos_per_channel(schedule: list[dict[str, Any]]) -> dict[str, int]:
    """실제 스케줄 결과 기준 채널별 배포 수 집계."""
    counts: dict[str, int] = {}
    for item in schedule:
        channel = str(item.get("channel") or "").strip()
        if not channel:
            continue
        counts[channel] = counts.get(channel, 0) + 1
    return counts


def count_videos_per_channel(topics: list[dict]) -> dict[str, int]:
    """Day 파일 주제 목록에서 채널별 영상 수를 계산합니다.

    Args:
        topics: get_today_topics() 반환값의 topics 리스트

    Returns:
        {"askanything": 4, "wonderdrop": 3, ...}
    """
    counts: dict[str, int] = {}
    for topic in topics:
        channels = topic.get("channels", {})
        for ch in channels:
            counts[ch] = counts.get(ch, 0) + 1
    return counts


def _ordered_channels(*count_maps: dict[str, int]) -> list[str]:
    """운영 채널 순서를 유지한 채 카운트 맵의 채널 목록을 병합."""
    channels: list[str] = []
    for channel in CHANNEL_WINDOWS:
        if any(channel in count_map for count_map in count_maps if isinstance(count_map, dict)):
            channels.append(channel)
    for count_map in count_maps:
        if not isinstance(count_map, dict):
            continue
        for channel in count_map:
            if channel not in channels:
                channels.append(channel)
    return channels


def _ordered_count_map(channels: list[str], counts: dict[str, int]) -> dict[str, int]:
    """지정한 채널 순서대로 카운트 맵을 정렬."""
    return {channel: int(counts.get(channel, 0) or 0) for channel in channels}


def summarize_schedule_counts(
    schedule: list[dict[str, Any]],
    target_date: datetime,
    *,
    requested_counts: dict[str, int] | None = None,
    rollout_notes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """스케줄 결과를 공개수/보류수/이월수 기준으로 요약."""
    target_kst = target_date.astimezone(KST) if target_date.tzinfo else target_date.replace(tzinfo=KST)
    target_day = target_kst.strftime("%Y-%m-%d")

    public_scheduled = count_scheduled_videos_per_channel(schedule)
    requested = requested_counts or public_scheduled

    holdback_counts: dict[str, int] = {}
    for note in rollout_notes or []:
        for channel in note.get("holdback_channels") or []:
            holdback_counts[channel] = holdback_counts.get(channel, 0) + 1

    publish_on_target_date: dict[str, int] = {}
    carryover_next_days: dict[str, int] = {}
    publish_dates: dict[str, dict[str, int]] = {}
    for item in schedule:
        channel = str(item.get("channel") or "").strip()
        if not channel:
            continue
        publish_dt = item.get("publish_at")
        if not isinstance(publish_dt, datetime):
            continue
        publish_kst = publish_dt.astimezone(KST)
        publish_day = publish_kst.strftime("%Y-%m-%d")
        day_bucket = publish_dates.setdefault(publish_day, {})
        day_bucket[channel] = day_bucket.get(channel, 0) + 1
        if publish_day == target_day:
            publish_on_target_date[channel] = publish_on_target_date.get(channel, 0) + 1
        elif publish_day > target_day:
            carryover_next_days[channel] = carryover_next_days.get(channel, 0) + 1

    final_expected: dict[str, int] = {}
    channels = _ordered_channels(
        requested,
        public_scheduled,
        holdback_counts,
        publish_on_target_date,
        carryover_next_days,
    )
    for channel in channels:
        final_expected[channel] = max(
            int(requested.get(channel, 0) or 0),
            int(public_scheduled.get(channel, 0) or 0) + int(holdback_counts.get(channel, 0) or 0),
        )

    ordered_publish_dates = {
        day: _ordered_count_map(_ordered_channels(counts), counts)
        for day, counts in sorted(publish_dates.items())
    }
    holdback_total = sum(holdback_counts.values())

    return {
        "requested_per_channel": _ordered_count_map(channels, requested),
        "public_scheduled_per_channel": _ordered_count_map(channels, public_scheduled),
        "holdback_per_channel": _ordered_count_map(channels, holdback_counts),
        "final_expected_per_channel": _ordered_count_map(channels, final_expected),
        "publish_on_target_date_per_channel": _ordered_count_map(channels, publish_on_target_date),
        "carryover_next_days_per_channel": _ordered_count_map(channels, carryover_next_days),
        "publish_dates": ordered_publish_dates,
        "rollout_overview": {
            "enabled": bool(rollout_notes),
            "lead_topics": len(rollout_notes or []),
            "holdback_total": holdback_total,
            "items": rollout_notes or [],
        },
    }


def calculate_schedule(topics: list[dict],
                       target_date: datetime | None = None,
                       *,
                       apply_rollout_strategy: bool = True) -> list[dict[str, Any]]:
    """Day 파일 주제에서 채널별 업로드 스케줄을 생성합니다.

    Args:
        topics: get_today_topics() 반환값의 topics 리스트
        target_date: 업로드 날짜 (None이면 오늘)

    Returns:
        [{"topic": str, "channel": str, "publish_at": datetime, "publish_at_iso": str}, ...]
        시간순 정렬
    """
    if target_date is None:
        target_date = datetime.now(KST)

    if apply_rollout_strategy:
        topics, _ = _apply_lead_channel_first(topics)

    # 날짜만 추출 (시간 제거)
    base_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)

    # 채널별 주제 목록 구성 (채널별 제목 포함)
    channel_topics: dict[str, list[dict]] = {}
    for topic in topics:
        topic_name = topic.get("topic_group", "unknown")
        format_type = topic.get("format_type", "FACT")
        channels = topic.get("channels", {})
        for ch, ch_data in channels.items():
            if ch not in channel_topics:
                channel_topics[ch] = []
            # 채널별 제목이 있으면 사용, 없으면 토픽명
            ch_title = ch_data.get("title", topic_name) if isinstance(ch_data, dict) else topic_name
            channel_topics[ch].append({
                "topic": topic_name,
                "title": ch_title,
                "format_type": format_type,
                "topic_group": topic_name,
                "_llm_topic_override": ch_data.get("source_topic") if isinstance(ch_data, dict) else None,
                "split_mode": topic.get("split_mode"),
                "series_title": topic.get("series_title"),
                "source_file": topic.get("source_file") or topic.get("day_file"),
                "day_file": topic.get("day_file") or topic.get("source_file"),
                "source_section": topic.get("source_section"),
                "rollout_strategy": topic.get("rollout_strategy"),
                "lead_channel": topic.get("lead_channel"),
                "holdback_channels": topic.get("holdback_channels", []),
                "holdback_channel_data": topic.get("holdback_channel_data", {}),
            })

    # 채널별 시간 분배
    schedule = []
    for ch, ch_topics in channel_topics.items():
        schedule.extend(_schedule_channel_items(ch, ch_topics, base_date))

    # 시간순 정렬
    schedule.sort(key=lambda x: x["publish_at"])

    return schedule


def format_schedule_table(schedule: list[dict]) -> str:
    """스케줄을 보기 좋은 테이블 문자열로 변환."""
    if not schedule:
        return "스케줄 없음"

    spans_multiple_days = len({item["publish_at"].date() for item in schedule}) > 1
    time_header = "날짜/시간 (KST)" if spans_multiple_days else "시간 (KST)"
    lines = [f"{time_header:<16} | 채널           | 주제"]
    lines.append("-" * 60)
    for item in schedule:
        time_str = item["publish_at"].strftime("%m-%d %H:%M") if spans_multiple_days else item["publish_at"].strftime("%H:%M")
        ch = item["channel"][:15].ljust(15)
        topic = (item.get("title") or item["topic"])[:30]
        lines.append(f"{time_str}        | {ch} | {topic}")

    return "\n".join(lines)


def get_schedule_summary(topics: list[dict],
                         target_date: datetime | None = None) -> dict[str, Any]:
    """스케줄 요약 — API 응답용."""
    planned_topics, rollout_notes = _apply_lead_channel_first(topics)
    schedule = calculate_schedule(planned_topics, target_date, apply_rollout_strategy=False)
    requested_counts = count_videos_per_channel(topics)
    target = target_date or datetime.now(KST)
    count_summary = summarize_schedule_counts(
        schedule,
        target,
        requested_counts=requested_counts,
        rollout_notes=rollout_notes,
    )

    return {
        "date": target.strftime("%Y-%m-%d"),
        "total_videos": len(schedule),
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
        "schedule": [
            {
                "topic": s.get("title") or s["topic"],
                "topic_group": s["topic"],
                "channel": s["channel"],
                "source_topic": s.get("_llm_topic_override") or s["topic"],
                "time_kst": s["publish_at_kst"],
                "publish_at": s["publish_at_iso"],
                "day_offset": s.get("day_offset", 0),
                "split_mode": s.get("split_mode"),
                "rollout_strategy": s.get("rollout_strategy"),
                "lead_channel": s.get("lead_channel"),
                "holdback_channels": s.get("holdback_channels", []),
            }
            for s in schedule
        ],
        "table": format_schedule_table(schedule),
        "rollout": rollout_notes,
        "rollout_overview": count_summary["rollout_overview"],
    }
