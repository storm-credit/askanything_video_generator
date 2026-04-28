"""YouTube 채널 성과 데이터 수집 — Data API v3로 영상 통계 자동 수집.

사용법:
  stats = fetch_channel_stats("askanything")
  # → {"channel": "askanything", "videos": [...], "summary": {...}}
"""
import os
import json
import requests
from datetime import datetime, timedelta
from typing import Any


# 채널 ID 매핑 (YouTube upload에서 사용하는 것과 동일)
CHANNEL_IDS = {
    "askanything": "UCxxxxxxxx",  # channel_accounts.json에서 로드
    "wonderdrop": "UCxxxxxxxx",
    "exploratodo": "UCxxxxxxxx",
    "prismtale": "UCxxxxxxxx",
}

# 채널별 API 키
CHANNEL_API_KEYS = {
    "askanything": os.getenv("YOUTUBE_API_KEY_ASKANYTHING", ""),
    "wonderdrop": os.getenv("YOUTUBE_API_KEY_WONDERDROP", ""),
    "exploratodo": os.getenv("YOUTUBE_API_KEY_EXPLORATODO", ""),
    "prismtale": os.getenv("YOUTUBE_API_KEY_PRISMTALE", os.getenv("YOUTUBE_API_KEY_EXPLORATODO", "")),
}

# 캐시 파일 경로
STATS_CACHE_DIR = os.path.join("assets", "_stats")


def _load_channel_ids() -> dict[str, str]:
    """youtube_tokens/channel_accounts.json에서 채널 ID 로드."""
    accounts_path = os.path.join("youtube_tokens", "channel_accounts.json")
    if not os.path.exists(accounts_path):
        return {}
    try:
        with open(accounts_path, "r") as f:
            data = json.load(f)
        result = {}
        for ch_name, ch_data in data.items():
            if "youtube" in ch_data:
                result[ch_name] = ch_data["youtube"]
        return result
    except Exception:
        return {}


def _get_channel_id(channel: str) -> str | None:
    """채널 이름으로 YouTube 채널 ID 조회."""
    ids = _load_channel_ids()
    return ids.get(channel)


def _get_api_key(channel: str) -> str:
    """채널별 API 키 반환."""
    return CHANNEL_API_KEYS.get(channel, "")


def fetch_channel_videos(channel: str, max_results: int = 50) -> list[dict[str, Any]]:
    """채널의 최근 영상 목록 + 통계를 가져옵니다.

    Returns:
        list of {"video_id", "title", "published_at", "views", "likes", "comments", "duration"}
    """
    channel_id = _get_channel_id(channel)
    api_key = _get_api_key(channel)

    if not channel_id or not api_key:
        print(f"[YouTube Stats] {channel}: 채널 ID 또는 API 키 없음")
        return []

    # 1단계: 채널 업로드 재생목록 ID 가져오기
    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/channels",
            params={
                "part": "contentDetails",
                "id": channel_id,
                "key": api_key,
            },
            timeout=10,
        )
        data = resp.json()
        uploads_id = data["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    except Exception as e:
        print(f"[YouTube Stats] {channel}: 채널 정보 조회 실패 — {e}")
        return []

    # 2단계: 업로드 재생목록에서 영상 ID 목록
    video_ids = []
    next_page = None
    while len(video_ids) < max_results:
        try:
            params: dict = {
                "part": "snippet",
                "playlistId": uploads_id,
                "maxResults": min(50, max_results - len(video_ids)),
                "key": api_key,
            }
            if next_page:
                params["pageToken"] = next_page
            resp = requests.get(
                "https://www.googleapis.com/youtube/v3/playlistItems",
                params=params,
                timeout=10,
            )
            data = resp.json()
            for item in data.get("items", []):
                video_ids.append({
                    "video_id": item["snippet"]["resourceId"]["videoId"],
                    "title": item["snippet"]["title"],
                    "published_at": item["snippet"]["publishedAt"],
                })
            next_page = data.get("nextPageToken")
            if not next_page:
                break
        except Exception as e:
            print(f"[YouTube Stats] {channel}: 영상 목록 조회 실패 — {e}")
            break

    if not video_ids:
        return []

    # 3단계: 영상별 통계 조회 (50개씩 배치)
    results = []
    for batch_start in range(0, len(video_ids), 50):
        batch = video_ids[batch_start:batch_start + 50]
        ids_str = ",".join(v["video_id"] for v in batch)
        try:
            resp = requests.get(
                "https://www.googleapis.com/youtube/v3/videos",
                params={
                    "part": "statistics,contentDetails",
                    "id": ids_str,
                    "key": api_key,
                },
                timeout=10,
            )
            stats_data = resp.json()
            stats_map = {}
            for item in stats_data.get("items", []):
                stats_map[item["id"]] = {
                    "views": int(item["statistics"].get("viewCount", 0)),
                    "likes": int(item["statistics"].get("likeCount", 0)),
                    "comments": int(item["statistics"].get("commentCount", 0)),
                    "duration": item["contentDetails"].get("duration", ""),
                }
        except Exception as e:
            print(f"[YouTube Stats] {channel}: 통계 조회 실패 — {e}")
            stats_map = {}

        for v in batch:
            stats = stats_map.get(v["video_id"], {})
            results.append({
                **v,
                "views": stats.get("views", 0),
                "likes": stats.get("likes", 0),
                "comments": stats.get("comments", 0),
                "duration": stats.get("duration", ""),
            })

    return results


def fetch_channel_stats(channel: str, max_results: int = 50) -> dict[str, Any]:
    """채널 통계 요약 + 영상별 데이터."""
    videos = fetch_channel_videos(channel, max_results)

    if not videos:
        return {"channel": channel, "videos": [], "summary": {}}

    try:
        from modules.utils.upload_history import upsert_videos

        upsert_videos(channel, videos, source="youtube_api")
    except Exception as e:
        print(f"[YouTube Stats] {channel}: 업로드 히스토리 DB 저장 실패 — {e}")

    total_views = sum(v["views"] for v in videos)
    avg_views = total_views / len(videos) if videos else 0

    # 상위 5개 영상
    top_videos = sorted(videos, key=lambda v: v["views"], reverse=True)[:5]

    # 최근 7일 영상
    week_ago = (datetime.now() - timedelta(days=7)).isoformat()
    recent = [v for v in videos if v["published_at"] >= week_ago]

    summary = {
        "total_videos": len(videos),
        "total_views": total_views,
        "avg_views": round(avg_views),
        "top_5": [{"title": v["title"], "views": v["views"]} for v in top_videos],
        "recent_7d_count": len(recent),
        "recent_7d_views": sum(v["views"] for v in recent),
        "fetched_at": datetime.now().isoformat(),
    }

    result = {"channel": channel, "videos": videos, "summary": summary}

    # 캐시 저장
    os.makedirs(STATS_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(STATS_CACHE_DIR, f"{channel}_stats.json")
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

    return result


def fetch_video_stats(channel: str, video_id: str) -> dict[str, Any] | None:
    """단일 YouTube 영상 통계를 가져온다."""
    api_key = _get_api_key(channel)
    if not api_key or not video_id:
        return None
    try:
        resp = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={
                "part": "snippet,statistics,contentDetails",
                "id": video_id,
                "key": api_key,
            },
            timeout=10,
        )
        data = resp.json()
        item = (data.get("items") or [None])[0]
        if not item:
            return None
        return {
            "video_id": item.get("id", video_id),
            "title": item.get("snippet", {}).get("title", ""),
            "published_at": item.get("snippet", {}).get("publishedAt", ""),
            "views": int(item.get("statistics", {}).get("viewCount", 0)),
            "likes": int(item.get("statistics", {}).get("likeCount", 0)),
            "comments": int(item.get("statistics", {}).get("commentCount", 0)),
            "duration": item.get("contentDetails", {}).get("duration", ""),
        }
    except Exception as e:
        print(f"[YouTube Stats] {channel}: 단일 영상 통계 조회 실패 — {e}")
        return None


def fetch_all_channels_stats() -> dict[str, Any]:
    """모든 채널의 통계를 수집합니다."""
    channels = _load_channel_ids()
    all_stats = {}
    for ch in channels:
        print(f"[YouTube Stats] {ch} 채널 통계 수집 중...")
        all_stats[ch] = fetch_channel_stats(ch)
        print(f"  → {all_stats[ch]['summary'].get('total_videos', 0)}개 영상, 총 {all_stats[ch]['summary'].get('total_views', 0)} 조회")
    return all_stats


def get_cached_stats(channel: str) -> dict[str, Any] | None:
    """캐시된 통계 반환 (없으면 None)."""
    cache_path = os.path.join(STATS_CACHE_DIR, f"{channel}_stats.json")
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None
