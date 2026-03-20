import os
import time
import secrets
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
TOKENS_DIR = Path("youtube_tokens")
CLIENT_SECRETS_DIR = Path("client_secrets")
CLIENT_SECRET_PATH = Path(os.getenv("YOUTUBE_CLIENT_SECRET", "client_secret.json"))  # 기본 fallback
REDIRECT_URI = os.getenv("YOUTUBE_REDIRECT_URI", f"http://localhost:{os.getenv('API_PORT', '8003')}/api/youtube/callback")

# 채널별 client_secret 매핑 (채널 프리셋 이름 → client_secret 파일명)
_CHANNEL_CLIENT_MAP: dict[str, str] = {}


def register_channel_client(channel_name: str, client_secret_filename: str):
    """채널에 특정 OAuth 클라이언트를 매핑합니다."""
    _CHANNEL_CLIENT_MAP[channel_name] = client_secret_filename


def _get_client_secret_path(channel_name: str | None = None) -> Path:
    """채널에 매핑된 client_secret 경로를 반환. 없으면 기본 fallback."""
    if channel_name and channel_name in _CHANNEL_CLIENT_MAP:
        p = CLIENT_SECRETS_DIR / _CHANNEL_CLIENT_MAP[channel_name]
        if p.exists():
            return p
    # client_secrets 폴더에 채널명과 같은 파일이 있으면 사용
    if channel_name:
        p = CLIENT_SECRETS_DIR / f"{channel_name}.json"
        if p.exists():
            return p
    # 기본 fallback
    return CLIENT_SECRET_PATH

# CSRF state 저장 (state → 만료 시간)
_pending_states: dict[str, float] = {}


def _ensure_tokens_dir():
    TOKENS_DIR.mkdir(exist_ok=True)


def _get_channel_info(creds: Credentials) -> dict:
    """OAuth 토큰으로 채널 이름과 ID를 조회합니다."""
    youtube = build("youtube", "v3", credentials=creds)
    response = youtube.channels().list(part="snippet", mine=True).execute()
    if response.get("items"):
        ch = response["items"][0]
        return {"id": ch["id"], "title": ch["snippet"]["title"]}
    return {"id": "unknown", "title": "Unknown Channel"}


def _get_credentials(channel_id: str = None) -> Credentials | None:
    """채널 ID로 저장된 토큰을 로드합니다. channel_id 없으면 첫 번째 토큰."""
    _ensure_tokens_dir()

    if channel_id:
        token_path = TOKENS_DIR / f"{channel_id}.json"
        if not token_path.exists():
            return None
    else:
        # 첫 번째 토큰 파일 사용
        tokens = list(TOKENS_DIR.glob("*.json"))
        if not tokens:
            # 레거시 단일 토큰 마이그레이션
            legacy = Path("youtube_token.json")
            if legacy.exists():
                return Credentials.from_authorized_user_file(str(legacy), SCOPES)
            return None
        token_path = tokens[0]

    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
    if creds and creds.valid:
        return creds
    return None


def _save_credentials(creds: Credentials, channel_id: str) -> None:
    _ensure_tokens_dir()
    token_path = TOKENS_DIR / f"{channel_id}.json"
    token_path.write_text(creds.to_json())


def get_channels() -> list[dict]:
    """연동된 모든 YouTube 채널 목록을 반환합니다."""
    _ensure_tokens_dir()
    channels = []
    for token_file in sorted(TOKENS_DIR.glob("*.json")):
        channel_id = token_file.stem
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                token_file.write_text(creds.to_json())
            if creds and creds.valid:
                info = _get_channel_info(creds)
                channels.append({"id": info["id"], "title": info["title"], "connected": True})
            else:
                channels.append({"id": channel_id, "title": channel_id, "connected": False})
        except Exception as e:
            print(f"[YouTube] 채널 정보 로드 실패 ({channel_id}): {e}")
            channels.append({"id": channel_id, "title": channel_id, "connected": False})
    return channels


def get_auth_status() -> dict:
    """YouTube 연동 상태를 반환합니다."""
    # 채널별 client_secret 또는 기본 client_secret 중 하나라도 있으면 OK
    has_any_secret = CLIENT_SECRET_PATH.exists() or (CLIENT_SECRETS_DIR.exists() and any(CLIENT_SECRETS_DIR.glob("*.json")))
    if not has_any_secret:
        return {"connected": False, "reason": "client_secret 파일이 없습니다", "channels": []}
    channels = get_channels()
    connected = any(ch["connected"] for ch in channels)
    return {"connected": connected, "channels": channels}


def create_auth_url(channel: str | None = None) -> str:
    """OAuth 인증 URL을 생성합니다 (CSRF 보호용 state 포함)."""
    secret_path = _get_client_secret_path(channel)
    if not secret_path.exists():
        raise FileNotFoundError(f"client_secret 파일이 필요합니다: {secret_path}")

    state = secrets.token_urlsafe(16)

    # 만료된 state 정리
    now = time.time()
    expired = [s for s, _ in _pending_states.items() if _[0] < now]
    for s in expired:
        _pending_states.pop(s, None)

    flow = Flow.from_client_secrets_file(
        str(secret_path),
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
        state=state,
    )
    # state에 시크릿 경로 + PKCE code_verifier 저장 (콜백에서 토큰 교환에 필요)
    _pending_states[state] = (time.time() + 300, str(secret_path), flow.code_verifier)

    return auth_url


def handle_auth_callback(auth_code: str, state: str | None = None) -> dict:
    """OAuth 콜백에서 토큰을 교환하고 채널별로 저장합니다."""
    if not state:
        raise ValueError("CSRF state가 누락되었습니다. 다시 시도해주세요.")
    state_data = _pending_states.pop(state, None)
    if state_data is None:
        raise ValueError("인증 state가 유효하지 않습니다. 다시 시도해주세요.")
    expires_at, secret_path_str, code_verifier = state_data
    if time.time() > expires_at:
        raise ValueError("인증 state가 만료되었습니다. 다시 시도해주세요.")
    flow = Flow.from_client_secrets_file(
        secret_path_str,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    flow.code_verifier = code_verifier
    flow.fetch_token(code=auth_code)
    creds = flow.credentials

    # 채널 정보 조회 후 채널 ID로 저장
    info = _get_channel_info(creds)
    _save_credentials(creds, info["id"])

    return {"success": True, "message": f"YouTube 채널 '{info['title']}' 연동 완료", "channel": info}


def upload_video(
    video_path: str,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    privacy: str = "private",
    category_id: str = "22",
    channel_id: str = None,
    publish_at: str | None = None,
) -> dict:
    """YouTube에 동영상을 업로드합니다.

    publish_at: 예약 공개 시간 (ISO 8601, e.g. "2026-03-20T15:00:00Z").
               설정 시 privacyStatus가 자동으로 "private"으로 변경됩니다.
    """
    from datetime import datetime, timezone

    creds = _get_credentials(channel_id)
    if not creds:
        raise PermissionError("YouTube 인증이 필요합니다. 먼저 계정을 연동해주세요.")

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"동영상 파일을 찾을 수 없습니다: {video_path}")

    # 예약 공개 검증
    if publish_at:
        try:
            scheduled_dt = datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"예약 시간 형식이 올바르지 않습니다: {publish_at} (ISO 8601 필요)")
        if scheduled_dt <= datetime.now(timezone.utc):
            raise ValueError("예약 시간은 현재 시간 이후여야 합니다.")

    youtube = build("youtube", "v3", credentials=creds)

    status_body: dict = {
        "privacyStatus": "private" if publish_at else privacy,
        "selfDeclaredMadeForKids": False,
    }
    if publish_at:
        status_body["publishAt"] = publish_at

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": status_body,
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=5 * 1024 * 1024,  # 5MB chunks (256KB → 5MB, 업로드 속도 개선)
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    print(f"-> [YouTube] 업로드 시작: {title}")
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"   업로드 진행: {pct}%")

    video_id = response["id"]
    video_url = f"https://youtube.com/shorts/{video_id}"
    print(f"OK [YouTube] 업로드 완료! {video_url}")

    result = {
        "success": True,
        "video_id": video_id,
        "url": video_url,
        "title": title,
        "privacy": "private" if publish_at else privacy,
    }
    if publish_at:
        result["scheduled_at"] = publish_at
        print(f"   [YouTube] 예약 공개: {publish_at}")
    return result


def disconnect(channel_id: str = None) -> dict:
    """YouTube 연동을 해제합니다."""
    _ensure_tokens_dir()
    if channel_id:
        token_path = TOKENS_DIR / f"{channel_id}.json"
        if token_path.exists():
            token_path.unlink()
        return {"success": True, "message": f"채널 {channel_id} 연동 해제"}
    else:
        for f in TOKENS_DIR.glob("*.json"):
            f.unlink()
        return {"success": True, "message": "모든 YouTube 연동이 해제되었습니다"}
