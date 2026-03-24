import hashlib
import os
import shutil
import tempfile
import time

IMAGE_CACHE_DIR = os.path.join("assets", ".cache", "images")
CACHE_MAX_AGE = 7 * 24 * 3600  # 7 days


def get_cached_image(prompt: str) -> str | None:
    """Return cached image path if exists and not expired, else None."""
    h = hashlib.sha256(prompt.encode()).hexdigest()
    cached = os.path.join(IMAGE_CACHE_DIR, f"{h}.png")
    if os.path.exists(cached) and os.path.getsize(cached) > 0:
        if time.time() - os.path.getmtime(cached) > CACHE_MAX_AGE:
            try:
                os.remove(cached)
            except OSError:
                pass
            return None
        return cached
    return None


def invalidate_cache(prompt: str) -> None:
    """Remove cached image for given prompt."""
    h = hashlib.sha256(prompt.encode()).hexdigest()
    cached = os.path.join(IMAGE_CACHE_DIR, f"{h}.png")
    try:
        if os.path.exists(cached):
            os.remove(cached)
    except OSError:
        pass


def save_to_cache(prompt: str, image_path: str) -> None:
    """Copy generated image to cache using atomic write (tmp + rename)."""
    if not image_path or not os.path.exists(image_path):
        return
    os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)
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
