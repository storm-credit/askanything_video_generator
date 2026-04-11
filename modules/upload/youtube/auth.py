import os
import json
import time
import secrets
from pathlib import Path
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
_BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent  # project root
TOKENS_DIR = _BASE_DIR / "youtube_tokens"
CLIENT_SECRETS_DIR = _BASE_DIR / "client_secrets"
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
        # 첫 번째 토큰 파일 사용 (channel_accounts.json 제외)
        tokens = [t for t in TOKENS_DIR.glob("*.json") if t.name != "channel_accounts.json"]
        if not tokens:
            # 레거시 단일 토큰 마이그레이션
            legacy = Path("youtube_token.json")
            if legacy.exists():
                return Credentials.from_authorized_user_file(str(legacy), SCOPES)
            return None
        token_path = tokens[0]

    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            token_path.write_text(creds.to_json())
        except Exception as e:
            print(f"[YouTube] 토큰 갱신 실패 (재인증 필요): {e}")
            return None
    if creds and creds.valid:
        return creds
    return None


_CHANNEL_CACHE_FILE = TOKENS_DIR / "_channel_cache.json"


def _load_channel_cache() -> dict:
    """채널 ID → {id, title} 캐시 로드 (API 쿼터 절약)."""
    try:
        if _CHANNEL_CACHE_FILE.exists():
            return json.loads(_CHANNEL_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save_channel_cache(channel_id: str, info: dict):
    """채널 정보를 캐시에 저장."""
    try:
        _ensure_tokens_dir()
        cache = _load_channel_cache()
        cache[channel_id] = info
        _CHANNEL_CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[YouTube] 채널 캐시 저장 실패: {e}")


def _save_credentials(creds: Credentials, channel_id: str) -> None:
    _ensure_tokens_dir()
    token_path = TOKENS_DIR / f"{channel_id}.json"
    token_path.write_text(creds.to_json())


def get_channels() -> list[dict]:
    """연동된 모든 YouTube 채널 목록을 반환합니다.
    채널 정보는 캐시에서 읽어 API 쿼터를 절약합니다.
    """
    _ensure_tokens_dir()
    cache = _load_channel_cache()
    channels = []
    for token_file in sorted(TOKENS_DIR.glob("*.json")):
        if token_file.name in ("channel_accounts.json", "_channel_cache.json"):
            continue
        channel_id = token_file.stem
        try:
            creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                token_file.write_text(creds.to_json())
            if creds and creds.valid:
                # 캐시 우선 — API 호출 없이 채널 정보 반환
                cached = cache.get(channel_id)
                if cached:
                    channels.append({"id": cached["id"], "title": cached["title"], "connected": True})
                else:
                    # 캐시 미스 시에만 API 호출
                    try:
                        info = _get_channel_info(creds)
                        _save_channel_cache(info["id"], info)
                        channels.append({"id": info["id"], "title": info["title"], "connected": True})
                    except Exception as api_err:
                        print(f"[YouTube] 채널 API 호출 실패 ({channel_id}): {api_err}")
                        channels.append({"id": channel_id, "title": channel_id, "connected": True})
            else:
                channels.append({"id": channel_id, "title": channel_id, "connected": False})
        except Exception as e:
            print(f"[YouTube] 채널 정보 로드 실패 ({channel_id}): {e}")
            channels.append({"id": channel_id, "title": channel_id, "connected": False})
    return channels


def get_auth_status() -> dict:
    """YouTube 연동 상태를 반환합니다 (채널별 연동 상태 포함)."""
    has_any_secret = CLIENT_SECRET_PATH.exists() or (CLIENT_SECRETS_DIR.exists() and any(CLIENT_SECRETS_DIR.glob("*.json")))
    if not has_any_secret:
        return {"connected": False, "reason": "client_secret 파일이 없습니다", "channels": [], "channel_status": {}}
    channels = get_channels()
    connected = any(ch["connected"] for ch in channels)

    # 채널 프리셋별 연동 상태 매핑
    accounts_path = TOKENS_DIR / "channel_accounts.json"
    accounts = {}
    if accounts_path.exists():
        try:
            raw = accounts_path.read_text(encoding="utf-8")
            accounts = json.loads(raw)
        except Exception as e:
            print(f"[YT ERROR] channel_accounts.json 파싱 실패: {e}")
    else:
        print(f"[YT WARN] accounts_path 없음: {accounts_path}")
    connected_ids = {ch["id"] for ch in channels if ch.get("connected")}
    print(f"[YT DEBUG] connected_ids={connected_ids}, accounts={accounts}")
    channel_status = {}
    for preset_name in ["askanything", "wonderdrop", "exploratodo", "prismtale"]:
        mapped_id = accounts.get(preset_name, {}).get("youtube")
        is_connected = bool(mapped_id and mapped_id in connected_ids)
        print(f"[YT DEBUG] {preset_name}: mapped={mapped_id} in_set={mapped_id in connected_ids if mapped_id else 'N/A'} result={is_connected}")
        channel_status[preset_name] = is_connected

    return {"connected": connected, "channels": channels, "channel_status": channel_status}


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
        prompt="consent select_account",
        state=state,
    )
    # state에 시크릿 경로 + PKCE code_verifier + 채널 프리셋 이름 저장
    _pending_states[state] = (time.time() + 300, str(secret_path), flow.code_verifier, channel)

    return auth_url


def handle_auth_callback(auth_code: str, state: str | None = None) -> dict:
    """OAuth 콜백에서 토큰을 교환하고 채널별로 저장합니다."""
    if not state:
        raise ValueError("CSRF state가 누락되었습니다. 다시 시도해주세요.")
    state_data = _pending_states.pop(state, None)
    if state_data is None:
        raise ValueError("인증 state가 유효하지 않습니다. 다시 시도해주세요.")
    expires_at, secret_path_str, code_verifier, channel_preset = state_data
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
    # 쿼터 초과 시 토큰은 임시 ID로 저장하고 graceful 처리
    try:
        info = _get_channel_info(creds)
        _save_credentials(creds, info["id"])
        _save_channel_cache(info["id"], info)
    except Exception as e:
        err_str = str(e)
        if "quotaExceeded" in err_str or "403" in err_str:
            # 쿼터 초과: 채널 ID 모르지만 토큰은 저장
            fallback_id = f"pending_{channel_preset or 'unknown'}_{int(time.time())}"
            _save_credentials(creds, fallback_id)
            print(f"[YouTube] 쿼터 초과로 채널 정보 조회 실패 — 임시 ID '{fallback_id}'로 저장. 내일 재인증 필요.")
            return {
                "success": True,
                "warning": "YouTube API 쿼터 초과 — 채널 정보를 가져오지 못했습니다. 내일(쿼터 리셋 후) 다시 연동해주세요.",
                "channel": {"id": fallback_id, "title": channel_preset or "Unknown"},
            }
        raise

    # 채널 프리셋에 YouTube 계정 자동 매핑
    if channel_preset:
        from modules.utils.channel_config import set_upload_account
        set_upload_account(channel_preset, "youtube", info["id"])
        print(f"[YouTube] 채널 '{channel_preset}' → YouTube '{info['title']}' ({info['id']}) 자동 매핑 완료")

    return {"success": True, "message": f"YouTube 채널 '{info['title']}' 연동 완료", "channel": info}


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
            if f.name == "channel_accounts.json":
                continue
            f.unlink()
        return {"success": True, "message": "모든 YouTube 연동이 해제되었습니다"}
