"""Gemini 클라이언트 팩토리 — AI Studio / Vertex AI 전환 + 멀티 SA 키 자동 폴링.

.env 설정:
  GEMINI_BACKEND=ai_studio   (기본값) → API Key
  GEMINI_BACKEND=vertex_ai              → ADC 인증 (멀티 SA 키 지원)

Vertex AI 추가 설정:
  VERTEX_PROJECT=your-gcp-project-id
  VERTEX_LOCATION=us-central1  (기본값)
  GOOGLE_APPLICATION_CREDENTIALS=/app/vertex-sa-key.json

멀티 SA 키:
  vertex-sa-key.json          → 메인 (shortspulse)
  vertex-sa-key-wonderdrop.json → 폴백 (certain-upgrade)
  → 429 에러 시 자동으로 다음 SA 키로 전환
"""
import os
import glob
import time
import threading

_backend: str | None = None
_sa_key_files: list[str] = []
_current_sa_idx = 0
_sa_lock = threading.Lock()
_sa_blocked: dict[int, float] = {}  # idx → unblock_time


def _get_backend() -> str:
    global _backend
    if _backend is None:
        _backend = os.getenv("GEMINI_BACKEND", "ai_studio").lower().strip()
    return _backend


def _discover_sa_keys() -> list[str]:
    """프로젝트 루트에서 vertex-sa-key*.json 파일 자동 탐색."""
    global _sa_key_files
    if _sa_key_files:
        return _sa_key_files

    # Docker: /app/, 로컬: 프로젝트 루트
    search_paths = ["/app/", os.path.dirname(os.path.dirname(os.path.dirname(__file__)))]
    found = []
    for base in search_paths:
        found.extend(glob.glob(os.path.join(base, "vertex-sa-key*.json")))

    # 중복 제거 + 정렬 (메인 키 먼저)
    seen = set()
    unique = []
    for f in sorted(found):
        real = os.path.realpath(f)
        if real not in seen:
            seen.add(real)
            unique.append(f)

    _sa_key_files = unique
    if unique:
        print(f"[Gemini Client] {len(unique)}개 SA 키 발견: {[os.path.basename(f) for f in unique]}")
    return unique


def _get_next_sa_key() -> str | None:
    """다음 사용 가능한 SA 키 파일 반환. 429 블록된 키 스킵."""
    global _current_sa_idx
    keys = _discover_sa_keys()
    if not keys:
        return None

    with _sa_lock:
        now = time.time()
        # 모든 키 순회하며 사용 가능한 거 찾기
        for _ in range(len(keys)):
            idx = _current_sa_idx % len(keys)
            blocked_until = _sa_blocked.get(idx, 0)
            if now >= blocked_until:
                _current_sa_idx = idx + 1
                return keys[idx]
            _current_sa_idx += 1

        # 전부 블록됨 — 가장 빨리 풀리는 키 대기
        earliest_idx = min(_sa_blocked, key=_sa_blocked.get)
        wait = _sa_blocked[earliest_idx] - now
        if wait > 0:
            print(f"[Gemini Client] 모든 SA 키 블록됨, {wait:.0f}초 대기...")
            time.sleep(wait)
        _current_sa_idx = earliest_idx + 1
        return keys[earliest_idx]


def mark_sa_key_blocked(key_file: str, block_seconds: int = 60):
    """429 에러 시 해당 SA 키를 일시 블록."""
    keys = _discover_sa_keys()
    with _sa_lock:
        for i, f in enumerate(keys):
            if f == key_file or os.path.basename(f) == os.path.basename(key_file):
                _sa_blocked[i] = time.time() + block_seconds
                print(f"[Gemini Client] SA 키 블록: {os.path.basename(f)} ({block_seconds}초)")
                break


def create_gemini_client(api_key: str | None = None):
    """GEMINI_BACKEND 설정에 따라 적절한 genai.Client를 반환합니다.

    vertex_ai 모드: 멀티 SA 키 자동 폴링 지원
    """
    from google import genai

    backend = _get_backend()

    if backend == "vertex_ai":
        sa_key_file = _get_next_sa_key()
        if sa_key_file:
            # SA 키 파일에서 프로젝트 ID 추출
            import json
            with open(sa_key_file, "r") as f:
                sa_data = json.load(f)
            project = sa_data.get("project_id", os.getenv("VERTEX_PROJECT", ""))
            location = os.getenv("VERTEX_LOCATION", "us-central1")

            # GOOGLE_APPLICATION_CREDENTIALS 임시 설정
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = sa_key_file

            return genai.Client(
                vertexai=True,
                project=project,
                location=location,
            )
        else:
            # SA 키 없으면 기본 ADC
            project = os.getenv("VERTEX_PROJECT", "")
            location = os.getenv("VERTEX_LOCATION", "us-central1")
            return genai.Client(
                vertexai=True,
                project=project,
                location=location,
            )

    return genai.Client(api_key=api_key)


def get_backend_label() -> str:
    """현재 백엔드 라벨 반환."""
    backend = _get_backend()
    if backend == "vertex_ai":
        keys = _discover_sa_keys()
        return f"Vertex AI ({len(keys)} SA keys)"
    return "AI Studio"
