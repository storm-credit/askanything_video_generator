"""YouTube Analytics API 연동 — 완시율(averageViewPercentage) 수집.

YouTube Analytics API는 OAuth2 필수.
기존 youtube_tokens/ 의 OAuth 토큰을 재사용하되,
yt-analytics.readonly 스코프가 필요하므로 재인증 시 자동 추가됨.

사용:
    from modules.analytics.youtube_analytics import fetch_retention_data
    data = fetch_retention_data("askanything", days=7)
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_BASE_DIR = Path(__file__).resolve().parent.parent.parent
TOKENS_DIR = _BASE_DIR / "youtube_tokens"
CACHE_DIR = _BASE_DIR / "assets" / "_analytics" / "retention"

CHANNELS = ["askanything", "wonderdrop", "exploratodo", "prismtale"]

ANALYTICS_SCOPE = "https://www.googleapis.com/auth/yt-analytics.readonly"


def _load_channel_accounts() -> dict[str, str]:
    """채널 프리셋명 → YouTube channel ID."""
    path = TOKENS_DIR / "channel_accounts.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _get_analytics_credentials(channel_id: str):
    """OAuth2 크레덴셜 로드 — yt-analytics.readonly 스코프 포함 여부 확인."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    token_path = TOKENS_DIR / f"{channel_id}.json"
    if not token_path.exists():
        return None

    creds = Credentials.from_authorized_user_file(str(token_path))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")

    # 스코프 체크 — analytics 스코프 없으면 경고
    if creds.scopes and ANALYTICS_SCOPE not in creds.scopes:
        print(f"  [Analytics] 경고: {channel_id} 토큰에 yt-analytics.readonly 스코프 없음")
        print(f"  [Analytics] 재인증 필요: /api/youtube/auth?channel=<name>")
        return None

    return creds


def _build_analytics_service(creds):
    """YouTube Analytics API v2 클라이언트 생성."""
    from googleapiclient.discovery import build
    return build("youtubeAnalytics", "v2", credentials=creds)


def fetch_retention_data(channel: str, days: int = 7) -> dict[str, Any]:
    """채널의 최근 N일 영상별 완시율 조회.

    Returns:
        {
            "channel": str,
            "videos": [
                {"video_id": str, "title": str, "avg_view_percentage": float,
                 "avg_view_duration": float, "views": int},
                ...
            ],
            "channel_avg_retention": float,
            "fetched_at": str
        }
    """
    accounts = _load_channel_accounts()
    channel_id = accounts.get(channel)
    if not channel_id:
        return {"channel": channel, "error": f"채널 ID 없음: {channel}", "videos": []}

    creds = _get_analytics_credentials(channel_id)
    if not creds:
        return {"channel": channel, "error": "OAuth 토큰 없음 또는 스코프 부족", "videos": []}

    analytics = _build_analytics_service(creds)

    end_date = datetime.utcnow().strftime("%Y-%m-%d")
    start_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")

    try:
        response = analytics.reports().query(
            ids=f"channel=={channel_id}",
            startDate=start_date,
            endDate=end_date,
            metrics="averageViewPercentage,averageViewDuration,views",
            dimensions="video",
            sort="-views",
            maxResults=50,
        ).execute()
    except Exception as e:
        return {"channel": channel, "error": f"Analytics API 호출 실패: {e}", "videos": []}

    # 결과 파싱
    videos = []
    headers = [h["name"] for h in response.get("columnHeaders", [])]
    for row in response.get("rows", []):
        row_dict = dict(zip(headers, row))
        videos.append({
            "video_id": row_dict.get("video", ""),
            "avg_view_percentage": round(row_dict.get("averageViewPercentage", 0), 1),
            "avg_view_duration": round(row_dict.get("averageViewDuration", 0), 1),
            "views": int(row_dict.get("views", 0)),
        })

    # 타이틀 보강 (Data API 캐시에서)
    _enrich_titles(videos, channel)

    # 채널 평균 완시율
    percentages = [v["avg_view_percentage"] for v in videos if v["avg_view_percentage"] > 0]
    avg_retention = round(sum(percentages) / len(percentages), 1) if percentages else 0

    result = {
        "channel": channel,
        "period": f"{start_date} ~ {end_date}",
        "videos": videos,
        "channel_avg_retention": avg_retention,
        "total_videos": len(videos),
        "fetched_at": datetime.utcnow().isoformat(),
    }

    # 캐시 저장
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{channel}_retention.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def _enrich_titles(videos: list[dict], channel: str) -> None:
    """youtube_stats 캐시에서 제목 보강."""
    try:
        from modules.utils.youtube_stats import get_cached_stats
        stats = get_cached_stats(channel)
        if not stats:
            return
        title_map = {v["video_id"]: v["title"] for v in stats.get("videos", [])}
        for v in videos:
            v["title"] = title_map.get(v["video_id"], v.get("title", ""))
    except Exception:
        pass


def fetch_all_retention(days: int = 7) -> dict[str, Any]:
    """전 채널 완시율 일괄 조회."""
    results = {}
    for ch in CHANNELS:
        results[ch] = fetch_retention_data(ch, days)
    return results


def get_cached_retention(channel: str) -> dict[str, Any] | None:
    """캐시된 완시율 데이터 반환."""
    path = CACHE_DIR / f"{channel}_retention.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass
    return None


def get_low_retention_videos(channel: str, threshold: float = 30.0) -> list[dict]:
    """완시율 기준 이하 영상 목록 (기본 30% 미만)."""
    data = get_cached_retention(channel)
    if not data or not data.get("videos"):
        return []
    return [
        v for v in data["videos"]
        if 0 < v.get("avg_view_percentage", 100) < threshold
    ]
