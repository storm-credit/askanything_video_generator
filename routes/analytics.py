"""분석 + 통계 라우터 — /api/stats/*, /api/analytics/*"""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/stats/channel/{channel}")
async def get_channel_stats(channel: str, refresh: bool = False):
    from modules.utils.youtube_stats import fetch_channel_stats, get_cached_stats
    if not refresh:
        cached = get_cached_stats(channel)
        if cached:
            return {"success": True, **cached}
    stats = fetch_channel_stats(channel)
    if not stats.get("videos"):
        return {"success": False, "message": f"{channel} 채널 통계 수집 실패", "channel": channel}
    return {"success": True, **stats}


@router.get("/stats/all")
async def get_all_channel_stats(refresh: bool = False):
    from modules.utils.youtube_stats import fetch_all_channels_stats, get_cached_stats, _load_channel_ids
    channels = _load_channel_ids()
    results = {}
    for ch in channels:
        if not refresh:
            cached = get_cached_stats(ch)
            if cached:
                results[ch] = cached
                continue
        results[ch] = fetch_all_channels_stats().get(ch, {})
    return {"success": True, "channels": results}


@router.post("/analytics/snapshot")
async def analytics_snapshot(label: str = "auto", refresh: bool = True):
    from modules.analytics.performance_tracker import take_snapshot
    result = take_snapshot(label=label, refresh=refresh)
    channels_summary = {ch: {k: v for k, v in d.items() if k != "videos"} for ch, d in result.get("channels", {}).items()}
    return {"success": True, "label": result["label"], "timestamp": result["timestamp"], "channels": channels_summary}


@router.get("/analytics/snapshots")
async def analytics_list_snapshots():
    from modules.analytics.performance_tracker import list_snapshots
    return {"success": True, "snapshots": list_snapshots()}


@router.get("/analytics/compare")
async def analytics_compare(before: str = None, after: str = None):
    from modules.analytics.performance_tracker import compare_snapshots
    return {"success": True, **compare_snapshots(before, after)}


@router.get("/analytics/trend/{channel}")
async def analytics_trend(channel: str, days: int = 14):
    from modules.analytics.performance_tracker import get_daily_trend
    return {"success": True, "channel": channel, "trend": get_daily_trend(channel, days)}


@router.post("/analytics/record-daily")
async def analytics_record_daily():
    from modules.analytics.performance_tracker import record_daily
    return {"success": True, "data": record_daily()}


@router.get("/analytics/hooks/{channel}")
async def analytics_hooks(channel: str, refresh: bool = False):
    from modules.analytics.performance_tracker import analyze_hook_patterns
    return {"success": True, "channel": channel, "patterns": analyze_hook_patterns(channel, refresh)}


@router.get("/analytics/cross-channel")
async def analytics_cross_channel(refresh: bool = False):
    from modules.analytics.performance_tracker import analyze_topic_cross_channel
    return {"success": True, "topics": analyze_topic_cross_channel(refresh)}


@router.get("/analytics/global-topic-signals")
async def analytics_global_topic_signals(
    locale: str | None = None,
    category: str | None = None,
    format_hint: str | None = None,
    limit: int = 80,
):
    """외부 나라별/글로벌 벤치마크 토픽 신호 조회."""
    from modules.utils.global_topic_signals import list_signals

    signals = list_signals(
        locale=locale,
        category=category,
        format_hint=format_hint,
        limit=limit,
    )
    return {"success": True, "signals": signals, "total": len(signals)}


@router.post("/analytics/global-topic-signals/refresh")
async def analytics_global_topic_signals_refresh(force: bool = True):
    """외부 YouTube 100만뷰 벤치마크 신호를 수집한다."""
    from modules.utils.youtube_benchmark import refresh_global_topic_signals

    return refresh_global_topic_signals(force=force)


@router.get("/analytics/tone-report")
async def analytics_tone_report():
    from modules.analytics.performance_tracker import get_tone_change_report
    return {"success": True, **get_tone_change_report()}


@router.get("/analytics/failures")
async def analytics_failures(date: str = None):
    """실패 로그 요약 조회. date=YYYY-MM-DD로 필터."""
    from modules.orchestrator.agents.failure_analyzer import get_failure_summary
    return {"success": True, **get_failure_summary(date)}


@router.post("/analytics/alerts")
async def analytics_run_alerts(send_telegram: bool = True):
    """성과 이상 탐지 실행 — 아웃라이어/하락/바이럴."""
    from modules.analytics.alert_engine import run_alerts
    result = run_alerts(send_telegram=send_telegram)
    return {"success": True, **result}


@router.get("/analytics/alerts/history")
async def analytics_alert_history():
    """최근 알림 이력 조회."""
    from pathlib import Path
    import json
    path = Path("assets/_analytics/alerts/last_run.json")
    if path.exists():
        return {"success": True, **json.loads(path.read_text(encoding="utf-8"))}
    return {"success": True, "alerts": [], "message": "아직 실행된 알림 없음"}


@router.get("/analytics/retention/{channel}")
async def analytics_retention(channel: str, days: int = 7):
    """완시율(averageViewPercentage) 조회 — Analytics API OAuth 필요."""
    from modules.analytics.youtube_analytics import fetch_retention_data
    return {"success": True, **fetch_retention_data(channel, days)}


@router.get("/analytics/retention-all")
async def analytics_retention_all(days: int = 7):
    """전체 채널 완시율 일괄 조회."""
    from modules.analytics.youtube_analytics import fetch_all_retention
    return {"success": True, "channels": fetch_all_retention(days)}


@router.get("/analytics/low-retention/{channel}")
async def analytics_low_retention(channel: str, threshold: float = 30.0):
    """완시율 기준 미달 영상 목록."""
    from modules.analytics.youtube_analytics import get_low_retention_videos
    videos = get_low_retention_videos(channel, threshold)
    return {"success": True, "channel": channel, "threshold": threshold, "videos": videos}
