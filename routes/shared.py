"""라우터 간 공유 상태 + 유틸리티.

api_server.py의 모듈 레벨 변수들을 여기로 이동.
각 라우터가 이 모듈에서 필요한 것만 import.
"""

import os
import re
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

# ── 동시성 제어 ──
generate_semaphore = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENT_GENERATE", "3")))
cut_executor = ThreadPoolExecutor(max_workers=4)
image_semaphore = threading.Semaphore(3)

# ── 취소 토큰 ──
cancel_events: dict[str, tuple[threading.Event, float]] = {}
active_generation_ids: set[str] = set()
generation_lock = threading.Lock()
CANCEL_EVENT_TTL = 3600

# ── 세션 저장소 (prepare/render) ──
prepared_sessions: dict[str, dict] = {}
session_lock = threading.Lock()
SESSION_MAX_AGE = 3600
SESSION_MAX_COUNT = 10

# ── 배치 상태 ──
batch_running = False
batch_stop = threading.Event()

# ── YouTube URL 패턴 ──
YT_URL_PATTERN = re.compile(r"(?:https?://)?(?:www\.)?(?:youtube\.com|youtu\.be)/\S+")


def resolve_youtube_topic(topic: str, reference_url: str | None = None) -> tuple[str, str | None]:
    """YouTube URL을 topic에서 감지하면 제목+자막으로 교체."""
    ref_url = reference_url
    if YT_URL_PATTERN.search(topic):
        ref_url = ref_url or topic
        try:
            from modules.utils.youtube_extractor import extract_youtube_reference
            yt_ref = extract_youtube_reference(ref_url)
            if yt_ref and yt_ref.get("title"):
                yt_title = re.sub(r"#\S+", "", yt_ref["title"]).strip()
                transcript = yt_ref.get("transcript", "")
                if transcript:
                    topic = f"{yt_title}\n\n[원본 영상 내용]\n{transcript[:800].strip()}"
                else:
                    topic = yt_title
        except Exception:
            pass
    return topic, ref_url


# ── 음성 유틸리티 ──
VOICE_MAP = {
    "eric": {"id": "cjVigY5qzO86Huf0OWal", "label": "Eric (한국어 남성)", "lang": "ko"},
    "adam": {"id": "pNInz6obpgDQGcFmaJgB", "label": "Adam (영어 남성)", "lang": "en"},
    "daniel": {"id": "onwK4e9ZLuTAKqWW03F9", "label": "Daniel (스페인어 남성)", "lang": "es"},
    "ryan": {"id": "wViXBPUJJGdJBpMsMJGR", "label": "Ryan (영어 남성, 침착)", "lang": "en"},
    "dylan": {"id": "J3rFxKSS9JTLsYX5h1sW", "label": "Dylan (ES-LATAM 남성)", "lang": "es"},
    "serena": {"id": "pFZP5JQG7iQjIQuC4Bku", "label": "Serena (ES-US 여성)", "lang": "es"},
}

VOICE_ID_TO_NAME = {v["id"]: k for k, v in VOICE_MAP.items()}


def cleanup_sessions():
    """만료된 세션 정리."""
    import time
    now = time.time()
    with session_lock:
        expired = [sid for sid, s in prepared_sessions.items()
                   if now - s.get("created_at", 0) > SESSION_MAX_AGE]
        for sid in expired:
            del prepared_sessions[sid]
        while len(prepared_sessions) > SESSION_MAX_COUNT:
            oldest = min(prepared_sessions, key=lambda k: prepared_sessions[k].get("created_at", 0))
            del prepared_sessions[oldest]
