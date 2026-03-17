"""YouTube Shorts/영상 분석 → 레퍼런스 컨텍스트 추출 모듈"""

import os
import re
import threading
import time
import hashlib

_ref_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 3600  # 1시간
_CACHE_MAX = 50  # 최대 캐시 엔트리 수


def _parse_video_id(url: str) -> str | None:
    """YouTube URL에서 video_id를 추출한다. shorts/watch/youtu.be 모두 지원."""
    patterns = [
        r"shorts/([a-zA-Z0-9_-]{11})",
        r"[?&]v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"embed/([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _fetch_metadata_ytdlp(video_id: str) -> dict:
    """yt-dlp로 메타데이터를 추출한다 (API 쿼터 소비 0, 무료)."""
    if not re.fullmatch(r'[a-zA-Z0-9_-]{11}', video_id):
        return {}
    try:
        import subprocess, json as _json
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-download", "--no-warnings",
             f"https://www.youtube.com/watch?v={video_id}"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return {}
        data = _json.loads(result.stdout)
        return {
            "title": data.get("title", ""),
            "description": data.get("description", ""),
            "channel": data.get("channel", "") or data.get("uploader", ""),
            "tags": data.get("tags", []) or [],
            "view_count": int(data.get("view_count", 0) or 0),
            "like_count": int(data.get("like_count", 0) or 0),
        }
    except Exception as e:
        print(f"[YouTube 분석] yt-dlp 메타데이터 추출 실패: {e}")
        return {}


def _fetch_metadata(video_id: str, api_key: str) -> dict:
    """메타데이터 추출: yt-dlp (무료) → YouTube Data API (폴백)."""
    # 1순위: yt-dlp (API 쿼터 소비 0)
    result = _fetch_metadata_ytdlp(video_id)
    if result and result.get("title"):
        return result

    # 2순위: YouTube Data API v3 (쿼터 1유닛 소비)
    if not api_key:
        return {}
    try:
        from googleapiclient.discovery import build
        import httplib2
        http = httplib2.Http(timeout=30)
        youtube = build("youtube", "v3", developerKey=api_key, http=http)
        resp = youtube.videos().list(
            part="snippet,statistics",
            id=video_id,
        ).execute()

        items = resp.get("items", [])
        if not items:
            return {}

        snippet = items[0].get("snippet", {})
        stats = items[0].get("statistics", {})
        return {
            "title": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "channel": snippet.get("channelTitle", ""),
            "tags": snippet.get("tags", []),
            "view_count": int(stats.get("viewCount", 0)),
            "like_count": int(stats.get("likeCount", 0)),
        }
    except Exception as e:
        print(f"[YouTube 분석] YouTube API 메타데이터 추출 실패: {e}")
        return {}


def _fetch_transcript(video_id: str) -> str:
    """youtube-transcript-api v1.0+로 자막을 추출한다. 한국어 → 영어 → 아무 언어 순서."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        api = YouTubeTranscriptApi()

        # 한국어 → 영어 순서로 시도
        for lang in ["ko", "en"]:
            try:
                entries = api.fetch(video_id, languages=[lang])
                lines = [s.text for s in entries if s.text]
                if lines:
                    return " ".join(lines)
            except Exception:
                continue

        # 사용 가능한 자막 중 아무거나
        try:
            transcript_list = api.list(video_id)
            for t in transcript_list:
                try:
                    entries = t.fetch()
                    lines = [s.text for s in entries if s.text]
                    if lines:
                        return " ".join(lines)
                except Exception:
                    continue
        except Exception:
            pass

        return ""
    except Exception as e:
        print(f"[YouTube 분석] 자막 추출 실패 (자막 없는 영상일 수 있음): {e}")
        return ""


def _analyze_structure(transcript: str) -> dict:
    """자막 텍스트에서 쇼츠 구조를 간단히 분석한다."""
    if not transcript:
        return {"hook": "", "style": "unknown", "sentence_count": 0}

    sentences = re.split(r"[.!?。？！]\s*", transcript)
    sentences = [s.strip() for s in sentences if s.strip()]

    hook = sentences[0] if sentences else ""
    ending = sentences[-1] if sentences else ""

    # 말투 감지
    casual_markers = ["거든", "잖아", "걸?", "ㄹㅇ", "미쳤", "대박", "진짜"]
    formal_markers = ["입니다", "합니다", "습니다", "습니까"]

    casual_count = sum(1 for s in sentences for m in casual_markers if m in s)
    formal_count = sum(1 for s in sentences for m in formal_markers if m in s)
    style = "casual" if casual_count >= formal_count else "formal"

    # 결론 패턴
    question_ending = ending.endswith("?") or any(m in ending for m in ["걸?", "잖아?", "거든?"])

    return {
        "hook": hook[:100],
        "ending": ending[:100],
        "style": style,
        "sentence_count": len(sentences),
        "has_question_ending": question_ending,
        "estimated_duration_sec": len(transcript) / 5,  # rough estimate
    }


def extract_youtube_reference(url: str, api_key: str | None = None) -> dict:
    """
    YouTube URL → 레퍼런스 분석 결과를 반환한다.

    Returns:
        {
            "video_id": str,
            "title": str,
            "channel": str,
            "view_count": int,
            "transcript": str,
            "structure": { hook, ending, style, sentence_count, ... },
        }
    """
    video_id = _parse_video_id(url)
    if not video_id:
        print(f"[YouTube 분석] 유효한 YouTube URL이 아닙니다: {url}")
        return {}

    # 캐시 확인
    cache_key = hashlib.sha256(video_id.encode()).hexdigest()
    with _cache_lock:
        cached = _ref_cache.get(cache_key)
        if cached and time.time() - cached[0] < _CACHE_TTL:
            return cached[1]

    # API 키 결정
    key = api_key or os.getenv("GEMINI_API_KEY")

    print(f"-> [레퍼런스 분석] YouTube 영상 '{video_id}' 분석 중...")

    # 메타데이터 + 자막 병렬이면 좋지만, 간단하게 순차
    metadata = _fetch_metadata(video_id, key) if key else {}
    transcript = _fetch_transcript(video_id)
    structure = _analyze_structure(transcript)

    result = {
        "video_id": video_id,
        "title": metadata.get("title", ""),
        "channel": metadata.get("channel", ""),
        "description": metadata.get("description", ""),
        "tags": metadata.get("tags", []),
        "view_count": metadata.get("view_count", 0),
        "like_count": metadata.get("like_count", 0),
        "transcript": transcript,
        "structure": structure,
    }

    print(f"OK [레퍼런스 분석] 완료! 제목: {result['title']}, 자막 {len(transcript)}자 추출")

    # 캐시 저장 (만료 정리 + 크기 제한)
    with _cache_lock:
        now = time.time()
        expired = [k for k, (ts, _) in _ref_cache.items() if now - ts > _CACHE_TTL]
        for k in expired:
            _ref_cache.pop(k, None)
        if len(_ref_cache) >= _CACHE_MAX:
            oldest = min(_ref_cache, key=lambda k: _ref_cache[k][0])
            _ref_cache.pop(oldest, None)
        _ref_cache[cache_key] = (now, result)

    return result
