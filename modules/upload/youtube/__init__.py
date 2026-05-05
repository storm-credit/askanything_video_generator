# Re-export public symbols lazily for backwards compatibility.
# External code does: from modules.upload.youtube import upload_video, get_auth_status, etc.

from importlib import import_module
from typing import Any


_EXPORT_MODULES = {
    "SCOPES": "auth",
    "TOKENS_DIR": "auth",
    "CLIENT_SECRETS_DIR": "auth",
    "CLIENT_SECRET_PATH": "auth",
    "REDIRECT_URI": "auth",
    "register_channel_client": "auth",
    "get_channels": "auth",
    "get_auth_status": "auth",
    "create_auth_url": "auth",
    "handle_auth_callback": "auth",
    "disconnect": "auth",
    "_get_credentials": "auth",
    "_get_client_secret_path": "auth",
    "_get_channel_info": "auth",
    "_ensure_tokens_dir": "auth",
    "_save_credentials": "auth",
    "_load_channel_cache": "auth",
    "_save_channel_cache": "auth",
    "upload_video": "upload",
    "CHANNEL_PLAYLISTS": "playlists",
    "FORMAT_PLAYLISTS": "playlists",
    "PLAYLIST_CATEGORIES": "playlists",
    "ensure_playlists": "playlists",
    "add_to_playlist": "playlists",
    "add_to_format_playlist": "playlists",
    "add_to_series_playlist": "playlists",
    "classify_existing_videos": "playlists",
    "_detect_category": "playlists",
    "_get_playlist_lang": "playlists",
    "_build_related_comment": "engagement",
    "_post_pinned_comment": "engagement",
}

__all__ = sorted(_EXPORT_MODULES)


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if not module_name:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(f"{__name__}.{module_name}")
    value = getattr(module, name)
    globals()[name] = value
    return value
