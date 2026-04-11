# Re-export all public symbols for backwards compatibility
# External code does: from modules.upload.youtube import upload_video, get_auth_status, etc.

from .auth import (
    SCOPES,
    TOKENS_DIR,
    CLIENT_SECRETS_DIR,
    CLIENT_SECRET_PATH,
    REDIRECT_URI,
    register_channel_client,
    get_channels,
    get_auth_status,
    create_auth_url,
    handle_auth_callback,
    disconnect,
    _get_credentials,
    _get_client_secret_path,
    _get_channel_info,
    _ensure_tokens_dir,
    _save_credentials,
    _load_channel_cache,
    _save_channel_cache,
)

from .upload import upload_video

from .playlists import (
    CHANNEL_PLAYLISTS,
    FORMAT_PLAYLISTS,
    PLAYLIST_CATEGORIES,
    ensure_playlists,
    add_to_playlist,
    add_to_format_playlist,
    add_to_series_playlist,
    classify_existing_videos,
    _detect_category,
    _get_playlist_lang,
)

from .engagement import (
    _build_related_comment,
    _post_pinned_comment,
)
