"""성과 이상 탐지 + 알림 엔진.

3가지 감지:
1. 아웃라이어 — 채널 평균 대비 비정상적 고/저 조회수 영상
2. 하락 감지 — 3일 평균 vs 7일 평균 급감
3. 바이럴 감지 — 최근 3일 내 발행된 영상 중 채널 평균 3배+ 조회

사용:
    from modules.analytics.alert_engine import run_alerts
    results = run_alerts()  # 전체 채널 스캔 + Telegram 알림
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

CHANNELS = ["askanything", "wonderdrop", "exploratodo", "prismtale"]

# 임계값
OUTLIER_Z_THRESHOLD = 2.5       # Z-score 기준 아웃라이어
DROP_THRESHOLD_PCT = -20        # 3d avg vs 7d avg 하락률
VIRAL_MULTIPLIER = 3.0          # 채널 평균 대비 배수
VIRAL_MIN_VIEWS = 500           # 최소 조회수 (노이즈 필터)
ALERT_COOLDOWN_HOURS = 12       # 같은 영상 재알림 방지 시간

# 알림 이력 파일
_ALERT_HISTORY_DIR = Path("assets/_analytics/alerts")


def _load_alert_history() -> dict[str, str]:
    """이미 알림 보낸 영상 ID → 마지막 알림 시각."""
    path = _ALERT_HISTORY_DIR / "history.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _save_alert_history(history: dict[str, str]) -> None:
    _ALERT_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    (_ALERT_HISTORY_DIR / "history.json").write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _is_cooldown(video_id: str, history: dict[str, str]) -> bool:
    last = history.get(video_id)
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last)
        return (datetime.now(timezone.utc) - last_dt).total_seconds() < ALERT_COOLDOWN_HOURS * 3600
    except Exception:
        return False


def _mean_std(values: list[int | float]) -> tuple[float, float]:
    if not values:
        return 0.0, 1.0
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / max(n - 1, 1)
    return mean, variance ** 0.5


def detect_outliers(videos: list[dict], channel: str) -> list[dict[str, Any]]:
    """Z-score 기반 아웃라이어 감지."""
    if len(videos) < 5:
        return []

    views_list = [v.get("views", 0) for v in videos]
    mean, std = _mean_std(views_list)
    if std < 1:
        return []

    alerts = []
    for v in videos:
        views = v.get("views", 0)
        z = (views - mean) / std
        if z >= OUTLIER_Z_THRESHOLD:
            alerts.append({
                "type": "outlier_high",
                "channel": channel,
                "video_id": v.get("video_id", ""),
                "title": v.get("title", ""),
                "views": views,
                "z_score": round(z, 2),
                "channel_avg": round(mean),
                "message": f"조회수 {views:,} (평균 {round(mean):,}의 {views/mean:.1f}배)",
            })
        elif z <= -OUTLIER_Z_THRESHOLD:
            alerts.append({
                "type": "outlier_low",
                "channel": channel,
                "video_id": v.get("video_id", ""),
                "title": v.get("title", ""),
                "views": views,
                "z_score": round(z, 2),
                "channel_avg": round(mean),
                "message": f"조회수 {views:,} (평균 {round(mean):,}의 {views/max(mean,1):.1%})",
            })
    return alerts


def detect_performance_drop(channel: str) -> dict[str, Any] | None:
    """3일 평균 vs 7일 평균 비교 — 급감 감지."""
    try:
        from modules.analytics.performance_tracker import take_snapshot
        snapshot = take_snapshot(label="alert_check", refresh=True)
    except Exception:
        return None

    ch_data = snapshot.get("channels", {}).get(channel)
    if not ch_data:
        return None

    avg_3d = ch_data.get("recent_3d_avg", 0)
    avg_7d = ch_data.get("recent_7d_avg", 0)

    if avg_7d < 10:
        return None

    change_pct = ((avg_3d - avg_7d) / avg_7d) * 100

    if change_pct <= DROP_THRESHOLD_PCT:
        return {
            "type": "performance_drop",
            "channel": channel,
            "avg_3d": avg_3d,
            "avg_7d": avg_7d,
            "change_pct": round(change_pct, 1),
            "message": f"3일 평균 {avg_3d:,} vs 7일 평균 {avg_7d:,} ({change_pct:+.1f}%)",
        }
    return None


def detect_viral(videos: list[dict], channel: str, channel_avg: float) -> list[dict[str, Any]]:
    """최근 3일 내 발행 + 채널 평균 3배+ 조회 → 바이럴 감지."""
    if channel_avg < 1:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=3)
    alerts = []

    for v in videos:
        pub = v.get("published_at", "")
        views = v.get("views", 0)
        if views < VIRAL_MIN_VIEWS:
            continue

        try:
            pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
        except Exception:
            continue

        if pub_dt < cutoff:
            continue

        ratio = views / channel_avg
        if ratio >= VIRAL_MULTIPLIER:
            alerts.append({
                "type": "viral",
                "channel": channel,
                "video_id": v.get("video_id", ""),
                "title": v.get("title", ""),
                "views": views,
                "ratio": round(ratio, 1),
                "channel_avg": round(channel_avg),
                "message": f"바이럴! {views:,}회 (평균의 {ratio:.1f}배, 발행 {pub_dt.strftime('%m-%d')})",
            })
    return alerts


def _send_alert(alert: dict[str, Any]) -> None:
    """Telegram 알림 전송."""
    try:
        from modules.utils.notify import _send
    except ImportError:
        print(f"  [AlertEngine] notify 모듈 없음, 콘솔 출력: {alert['message']}")
        return

    type_emoji = {
        "outlier_high": "📈", "outlier_low": "📉",
        "performance_drop": "⚠️", "viral": "🔥",
    }
    emoji = type_emoji.get(alert["type"], "🔔")
    channel = alert.get("channel", "")
    title = alert.get("title", "")
    msg = alert.get("message", "")

    text = f"{emoji} <b>[{channel}]</b> {title}\n{msg}"

    buttons = []
    vid = alert.get("video_id")
    if vid:
        buttons = [{"text": "영상 보기", "url": f"https://youtube.com/shorts/{vid}"}]

    _send(text, silent=alert["type"] != "viral", buttons=buttons or None)


def run_alerts(channels: list[str] | None = None,
               send_telegram: bool = True) -> dict[str, Any]:
    """전체 채널 스캔 + 알림.

    Returns:
        {"alerts": [...], "channels_checked": int, "alerts_sent": int}
    """
    from modules.utils.youtube_stats import fetch_channel_stats

    target_channels = channels or CHANNELS
    history = _load_alert_history()
    all_alerts: list[dict] = []
    sent_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    for ch in target_channels:
        try:
            stats = fetch_channel_stats(ch, max_results=50)
        except Exception as e:
            print(f"  [AlertEngine] {ch} 통계 수집 실패: {e}")
            continue

        videos = stats.get("videos", [])
        summary = stats.get("summary", {})
        avg_views = summary.get("avg_views", 0)

        # 1) 아웃라이어
        outliers = detect_outliers(videos, ch)
        all_alerts.extend(outliers)

        # 2) 하락
        drop = detect_performance_drop(ch)
        if drop:
            all_alerts.append(drop)

        # 3) 바이럴
        virals = detect_viral(videos, ch, avg_views)
        all_alerts.extend(virals)

    # 알림 전송 (쿨다운 체크)
    for alert in all_alerts:
        vid = alert.get("video_id", alert.get("type", "") + "_" + alert.get("channel", ""))
        if _is_cooldown(vid, history):
            continue

        if send_telegram:
            _send_alert(alert)
        history[vid] = now_iso
        sent_count += 1
        print(f"  [AlertEngine] {alert['type']}: {alert.get('channel')} — {alert.get('message')}")

    _save_alert_history(history)

    result = {
        "alerts": all_alerts,
        "channels_checked": len(target_channels),
        "alerts_sent": sent_count,
        "checked_at": now_iso,
    }

    # 결과 저장
    _ALERT_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    (_ALERT_HISTORY_DIR / "last_run.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return result
