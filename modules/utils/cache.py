import hashlib
import os
import shutil

IMAGE_CACHE_DIR = os.path.join("assets", ".cache", "images")


def get_cached_image(prompt: str) -> str | None:
    """Return cached image path if exists, else None."""
    h = hashlib.md5(prompt.encode()).hexdigest()
    cached = os.path.join(IMAGE_CACHE_DIR, f"{h}.png")
    if os.path.exists(cached) and os.path.getsize(cached) > 0:
        return cached
    return None


def save_to_cache(prompt: str, image_path: str) -> None:
    """Copy generated image to cache."""
    if not image_path or not os.path.exists(image_path):
        return
    os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)
    h = hashlib.md5(prompt.encode()).hexdigest()
    cached = os.path.join(IMAGE_CACHE_DIR, f"{h}.png")
    try:
        shutil.copy2(image_path, cached)
    except OSError:
        pass
