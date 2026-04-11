"""채널별 업로드 시간 자동 분배 — Day 파일 기반 스케줄링.

Day 파일 → 채널별 영상 수 계산 → 시간 윈도우 내 균등 분배 → publishAt 생성
"""
from datetime import datetime, timedelta, timezone, time as dt_time
from typing import Any

# KST 타임존
KST = timezone(timedelta(hours=9))

# 채널별 최적 업로드 시간 윈도우 (KST 기준)
# ※ 이 시간은 YouTube publishAt (예약 공개 시간) — 시청자 피크에 맞춤
# ※ 배치(영상 생성)는 새벽 2~6시에 별도 실행, 여기서는 공개 시간만 제어
CHANNEL_WINDOWS = {
    "askanything": {
        "start": dt_time(21, 0),   # KST 21:00 — 한국 저녁 프라임 (21~24시 피크)
        "end": dt_time(23, 30),    # KST 23:30
        "min_interval_min": 45,
    },
    "wonderdrop": {
        "start": dt_time(8, 0),    # KST 08:00 = EST 19:00 — 미국 저녁 프라임
        "end": dt_time(11, 0),     # KST 11:00 = EST 22:00
        "min_interval_min": 45,
    },
    "exploratodo": {
        "start": dt_time(10, 0),   # KST 10:00 = CST 20:00 — 멕시코 저녁 프라임
        "end": dt_time(13, 0),     # KST 13:00 = CST 23:00
        "min_interval_min": 45,
    },
    "prismtale": {
        "start": dt_time(9, 0),    # KST 09:00 = EST 20:00 — US 히스패닉 저녁 (wonderdrop +1h 오프셋)
        "end": dt_time(12, 0),     # KST 12:00 = EST 23:00
        "min_interval_min": 45,
    },
}


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


def calculate_schedule(topics: list[dict],
                       target_date: datetime | None = None) -> list[dict[str, Any]]:
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
                "series_title": topic.get("series_title"),
            })

    # 채널별 시간 분배
    schedule = []
    for ch, ch_topics in channel_topics.items():
        window = CHANNEL_WINDOWS.get(ch)
        if not window:
            continue

        n = len(ch_topics)
        if n == 0:
            continue

        # 시간 윈도우 계산 (분) — KST timezone-aware
        start_dt = base_date.replace(hour=window["start"].hour, minute=window["start"].minute, tzinfo=KST)
        end_dt = base_date.replace(hour=window["end"].hour, minute=window["end"].minute, tzinfo=KST)
        window_minutes = (end_dt - start_dt).total_seconds() / 60

        # 간격 계산 (최소 간격 보장)
        if n == 1:
            interval_min = 0
        else:
            interval_min = max(
                window["min_interval_min"],
                window_minutes / n
            )

        # 각 영상 시간 배정
        for i, topic_item in enumerate(ch_topics):
            topic_name = topic_item["topic"] if isinstance(topic_item, dict) else topic_item
            topic_title = topic_item.get("title", topic_name) if isinstance(topic_item, dict) else topic_name
            publish_time = start_dt + timedelta(minutes=interval_min * i)

            # YouTube API용 ISO 8601 (UTC로 변환)
            publish_utc = publish_time.astimezone(timezone.utc)

            schedule.append({
                "topic": topic_name,
                "title": topic_title,  # 채널별 제목 (EN/ES 토픽명)
                "channel": ch,
                "topic_group": topic_item.get("topic_group", topic_name) if isinstance(topic_item, dict) else topic_name,
                "format_type": topic_item.get("format_type", "FACT") if isinstance(topic_item, dict) else "FACT",
                "publish_at_kst": publish_time.strftime("%Y-%m-%d %H:%M KST"),
                "publish_at_iso": publish_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "publish_at": publish_time,
                "order": i,
            })

    # 시간순 정렬
    schedule.sort(key=lambda x: x["publish_at"])

    return schedule


def format_schedule_table(schedule: list[dict]) -> str:
    """스케줄을 보기 좋은 테이블 문자열로 변환."""
    if not schedule:
        return "스케줄 없음"

    lines = ["시간 (KST)     | 채널           | 주제"]
    lines.append("-" * 60)
    for item in schedule:
        time_str = item["publish_at_kst"].split(" ")[1]  # HH:MM KST
        ch = item["channel"][:15].ljust(15)
        topic = item["topic"][:30]
        lines.append(f"{time_str}        | {ch} | {topic}")

    return "\n".join(lines)


def get_schedule_summary(topics: list[dict],
                         target_date: datetime | None = None) -> dict[str, Any]:
    """스케줄 요약 — API 응답용."""
    schedule = calculate_schedule(topics, target_date)
    counts = count_videos_per_channel(topics)

    return {
        "date": (target_date or datetime.now(KST)).strftime("%Y-%m-%d"),
        "total_videos": len(schedule),
        "per_channel": counts,
        "schedule": [
            {
                "topic": s["topic"],
                "channel": s["channel"],
                "time_kst": s["publish_at_kst"],
                "publish_at": s["publish_at_iso"],
            }
            for s in schedule
        ],
        "table": format_schedule_table(schedule),
    }
