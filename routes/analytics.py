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


@router.get("/analytics/tone-report")
async def analytics_tone_report():
    from modules.analytics.performance_tracker import get_tone_change_report
    return {"success": True, **get_tone_change_report()}


@router.get("/analytics/failures")
async def analytics_failures(date: str = None):
    """실패 로그 요약 조회. date=YYYY-MM-DD로 필터."""
    from modules.orchestrator.agents.failure_analyzer import get_failure_summary
    return {"success": True, **get_failure_summary(date)}
