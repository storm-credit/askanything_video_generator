import os
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
TOKENS_DIR = Path("youtube_tokens")
CLIENT_SECRET_PATH = Path(os.getenv("YOUTUBE_CLIENT_SECRET", "client_secret.json"))
REDIRECT_URI = os.getenv("YOUTUBE_REDIRECT_URI", "http://localhost:8003/api/youtube/callback")


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
        except Exception:
            channels.append({"id": channel_id, "title": channel_id, "connected": False})
    return channels


def get_auth_status() -> dict:
    """YouTube 연동 상태를 반환합니다."""
    if not CLIENT_SECRET_PATH.exists():
        return {"connected": False, "reason": "client_secret.json 파일이 없습니다", "channels": []}
    channels = get_channels()
    connected = any(ch["connected"] for ch in channels)
    return {"connected": connected, "channels": channels}


def create_auth_url() -> str:
    """OAuth 인증 URL을 생성합니다."""
    if not CLIENT_SECRET_PATH.exists():
        raise FileNotFoundError("client_secret.json 파일이 필요합니다. Google Cloud Console에서 다운로드하세요.")

    flow = Flow.from_client_secrets_file(
        str(CLIENT_SECRET_PATH),
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return auth_url


def handle_auth_callback(auth_code: str) -> dict:
    """OAuth 콜백에서 토큰을 교환하고 채널별로 저장합니다."""
    flow = Flow.from_client_secrets_file(
        str(CLIENT_SECRET_PATH),
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
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
) -> dict:
    """YouTube에 동영상을 업로드합니다."""
    creds = _get_credentials(channel_id)
    if not creds:
        raise PermissionError("YouTube 인증이 필요합니다. 먼저 계정을 연동해주세요.")

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"동영상 파일을 찾을 수 없습니다: {video_path}")

    youtube = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=256 * 1024,
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

    return {
        "success": True,
        "video_id": video_id,
        "url": video_url,
        "title": title,
        "privacy": privacy,
    }


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
