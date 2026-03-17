import hashlib
import os
import shutil
import tempfile
import threading
import time

IMAGE_CACHE_DIR = os.path.join("assets", ".cache", "images")
CACHE_MAX_AGE = 7 * 24 * 3600  # 7 days
CACHE_MAX_FILES = 200  # 최대 캐시 파일 수 (디스크 고갈 방지, ~1GB 상한)

_cache_lock = threading.Lock()


def get_cached_image(prompt: str) -> str | None:
    """Return cached image path if exists and not expired, else None."""
    h = hashlib.sha256(prompt.encode()).hexdigest()
    cached = os.path.join(IMAGE_CACHE_DIR, f"{h}.png")
    with _cache_lock:
        if os.path.exists(cached) and os.path.getsize(cached) > 0:
            if time.time() - os.path.getmtime(cached) > CACHE_MAX_AGE:
                try:
                    os.remove(cached)
                except OSError:
                    pass
                return None
            return cached
    return None


def _evict_oldest_files(max_files: int = CACHE_MAX_FILES) -> None:
    """캐시 파일 수가 max_files 초과 시 가장 오래된 파일 삭제 (lock 내부에서 호출)."""
    try:
        files = [
            os.path.join(IMAGE_CACHE_DIR, f)
            for f in os.listdir(IMAGE_CACHE_DIR)
            if f.endswith(".png")
        ]
        if len(files) <= max_files:
            return
        # 수정 시각 기준 정렬, 오래된 것부터 삭제
        files.sort(key=lambda p: os.path.getmtime(p))
        to_remove = len(files) - max_files
        for f in files[:to_remove]:
            try:
                os.remove(f)
            except OSError:
                pass
    except OSError:
        pass


def save_to_cache(prompt: str, image_path: str) -> None:
    """Copy generated image to cache using atomic write (tmp + rename)."""
    if not image_path or not os.path.exists(image_path):
        return
    with _cache_lock:
        os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)
        # 캐시 파일 수 제한 (디스크 고갈 방지)
        _evict_oldest_files()
        h = hashlib.sha256(prompt.encode()).hexdigest()
        cached = os.path.join(IMAGE_CACHE_DIR, f"{h}.png")
        tmp = None
        try:
            fd, tmp = tempfile.mkstemp(dir=IMAGE_CACHE_DIR, suffix=".tmp")
            os.close(fd)
            shutil.copy2(image_path, tmp)
            os.replace(tmp, cached)  # atomic on same filesystem
        except OSError:
            if tmp:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
