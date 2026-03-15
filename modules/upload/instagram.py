import os
import json
import time
import secrets
import requests
from pathlib import Path

# Instagram Graph API - Reels Publishing
# Requires: Facebook App + Instagram Business/Creator account
# Docs: https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/content-publishing

FB_APP_ID = os.getenv("INSTAGRAM_APP_ID", "")
FB_APP_SECRET = os.getenv("INSTAGRAM_APP_SECRET", "")
REDIRECT_URI = os.getenv("INSTAGRAM_REDIRECT_URI", "http://localhost:8003/api/instagram/callback")
TOKENS_DIR = Path("instagram_tokens")

SCOPES = "instagram_basic,instagram_content_publish"
GRAPH_API_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# CSRF state 저장
_pending_states: dict[str, float] = {}


def _ensure_tokens_dir():
    TOKENS_DIR.mkdir(exist_ok=True)


def _load_token(account_id: str = "default") -> dict | None:
    _ensure_tokens_dir()
    path = TOKENS_DIR / f"{account_id}.json"
    if not path.exists():
        tokens = list(TOKENS_DIR.glob("*.json"))
        if not tokens:
            return None
        path = tokens[0]
    try:
        data = json.loads(path.read_text())
        if data.get("expires_at", 0) < time.time():
            refreshed = _refresh_token(data)
            if refreshed:
                return refreshed
            return None
        return data
    except (json.JSONDecodeError, KeyError, OSError) as e:
        print(f"[Instagram] 토큰 로드 실패 ({path}): {e}")
        return None


def _save_token(token_data: dict, account_id: str = "default") -> None:
    _ensure_tokens_dir()
    path = TOKENS_DIR / f"{account_id}.json"
    path.write_text(json.dumps(token_data, indent=2))


def _refresh_token(token_data: dict) -> dict | None:
    access_token = token_data.get("access_token")
    if not access_token:
        return None
    try:
        resp = requests.get(
            f"{GRAPH_BASE}/oauth/access_token",
            params={
                "grant_type": "fb_exchange_token",
                "client_id": FB_APP_ID,
                "client_secret": FB_APP_SECRET,
                "fb_exchange_token": access_token,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            new_token = {
                **token_data,
                "access_token": data["access_token"],
                "expires_at": time.time() + data.get("expires_in", 5184000),
            }
            _save_token(new_token, token_data.get("ig_user_id", "default"))
            return new_token
    except Exception as e:
        print(f"[Instagram] 토큰 갱신 실패: {e}")
    return None


def _get_ig_user_id(access_token: str) -> str | None:
    """Instagram Business Account ID 조회 (Facebook Page 연결 필요)"""
    try:
        resp = requests.get(
            f"{GRAPH_BASE}/me/accounts",
            params={"access_token": access_token, "fields": "instagram_business_account,name"},
            timeout=15,
        )
        if resp.status_code == 200:
            pages = resp.json().get("data", [])
            for page in pages:
                ig_account = page.get("instagram_business_account")
                if ig_account:
                    return ig_account["id"]
    except Exception as e:
        print(f"[Instagram] IG 계정 조회 실패: {e}")
    return None


def get_auth_status() -> dict:
    if not FB_APP_ID or not FB_APP_SECRET:
        return {"connected": False, "reason": "INSTAGRAM_APP_ID/SECRET 환경 변수가 설정되지 않았습니다", "accounts": []}
    _ensure_tokens_dir()
    accounts = []
    for token_file in sorted(TOKENS_DIR.glob("*.json")):
        account_id = token_file.stem
        token = _load_token(account_id)
        accounts.append({
            "id": account_id,
            "username": token.get("username", account_id) if token else account_id,
            "connected": token is not None,
        })
    return {"connected": len(accounts) > 0 and any(a["connected"] for a in accounts), "accounts": accounts}


def create_auth_url() -> str:
    if not FB_APP_ID:
        raise ValueError("INSTAGRAM_APP_ID 환경 변수가 필요합니다")
    state = secrets.token_urlsafe(16)
    _pending_states[state] = time.time() + 300
    # 만료된 state 정리
    now = time.time()
    expired = [s for s, exp in _pending_states.items() if exp < now]
    for s in expired:
        _pending_states.pop(s, None)

    url = (
        f"https://www.facebook.com/{GRAPH_API_VERSION}/dialog/oauth"
        f"?client_id={FB_APP_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope={SCOPES}"
        f"&response_type=code"
        f"&state={state}"
    )
    return url


def handle_auth_callback(code: str, state: str | None = None) -> dict:
    if state:
        expires_at = _pending_states.pop(state, None)
        if expires_at is None or time.time() > expires_at:
            raise ValueError("인증 state가 유효하지 않습니다. 다시 시도해주세요.")

    # 단기 토큰 교환
    resp = requests.get(
        f"{GRAPH_BASE}/oauth/access_token",
        params={
            "client_id": FB_APP_ID,
            "client_secret": FB_APP_SECRET,
            "redirect_uri": REDIRECT_URI,
            "code": code,
        },
        timeout=15,
    )
    if resp.status_code != 200:
        raise Exception(f"Instagram 토큰 교환 실패: {resp.text}")

    short_token = resp.json()["access_token"]

    # 장기 토큰으로 교환
    long_resp = requests.get(
        f"{GRAPH_BASE}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": FB_APP_ID,
            "client_secret": FB_APP_SECRET,
            "fb_exchange_token": short_token,
        },
        timeout=15,
    )
    if long_resp.status_code != 200:
        raise Exception(f"Instagram 장기 토큰 교환 실패: {long_resp.text}")

    long_data = long_resp.json()
    access_token = long_data["access_token"]

    ig_user_id = _get_ig_user_id(access_token)
    if not ig_user_id:
        raise Exception("Instagram Business 계정을 찾을 수 없습니다. Facebook Page에 Instagram 계정이 연결되어 있는지 확인해주세요.")

    username = ig_user_id
    try:
        user_resp = requests.get(
            f"{GRAPH_BASE}/{ig_user_id}",
            params={"access_token": access_token, "fields": "username"},
            timeout=10,
        )
        if user_resp.status_code == 200:
            username = user_resp.json().get("username", ig_user_id)
    except Exception:
        pass

    token_data = {
        "access_token": access_token,
        "ig_user_id": ig_user_id,
        "username": username,
        "expires_at": time.time() + long_data.get("expires_in", 5184000),
    }
    _save_token(token_data, ig_user_id)

    return {"success": True, "message": f"Instagram 계정 @{username} 연동 완료", "account": {"id": ig_user_id, "username": username}}


def upload_reels(
    video_path: str,
    caption: str = "",
    account_id: str | None = None,
    video_url: str | None = None,
) -> dict:
    """Instagram Reels로 동영상을 업로드합니다.

    Instagram Graph API는 video_url (공개 URL)이 필요합니다.
    로컬 파일인 경우 video_url을 별도로 제공해야 합니다.
    """
    token = _load_token(account_id or "default")
    if not token:
        raise PermissionError("Instagram 인증이 필요합니다. 먼저 계정을 연동해주세요.")

    access_token = token["access_token"]
    ig_user_id = token["ig_user_id"]

    if not video_url and not os.path.exists(video_path):
        raise FileNotFoundError(f"동영상 파일을 찾을 수 없습니다: {video_path}")

    # Instagram은 공개 URL을 요구 — 로컬 파일 경로를 서버 URL로 변환
    if not video_url:
        server_host = os.getenv("PUBLIC_SERVER_URL", "").rstrip("/")
        if not server_host:
            raise ValueError(
                "Instagram Reels 업로드에는 공개 URL이 필요합니다. "
                "PUBLIC_SERVER_URL 환경 변수를 설정하거나, ngrok 등으로 서버를 외부 노출해주세요."
            )
        # assets/ 디렉토리 기준 상대 경로 추출 (안전하게)
        abs_path = os.path.abspath(video_path)
        assets_base = os.path.abspath("assets")
        try:
            rel = Path(abs_path).relative_to(assets_base)
            video_url = f"{server_host}/assets/{rel.as_posix()}"
        except ValueError:
            raise ValueError(f"assets 디렉토리 외부의 파일은 업로드할 수 없습니다: {video_path}")

    print(f"-> [Instagram] Reels 업로드 시작: {caption[:50]}...")

    # Step 1: Create media container
    create_resp = requests.post(
        f"{GRAPH_BASE}/{ig_user_id}/media",
        params={
            "access_token": access_token,
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption[:2200],
            "share_to_feed": "true",
        },
        timeout=30,
    )
    if create_resp.status_code != 200:
        raise Exception(f"Instagram 미디어 생성 실패: {create_resp.text}")

    container_id = create_resp.json().get("id")
    if not container_id:
        raise Exception("Instagram 미디어 컨테이너 ID를 받지 못했습니다")

    # Step 2: Wait for processing (polling)
    print("   Instagram 영상 처리 중...")
    for attempt in range(30):
        time.sleep(5)
        status_resp = requests.get(
            f"{GRAPH_BASE}/{container_id}",
            params={"access_token": access_token, "fields": "status_code"},
            timeout=15,
        )
        if status_resp.status_code == 200:
            status = status_resp.json().get("status_code")
            if status == "FINISHED":
                break
            elif status == "ERROR":
                raise Exception("Instagram 영상 처리 실패")
            print(f"   처리 중... ({status})")
    else:
        raise Exception("Instagram 영상 처리 타임아웃 (2.5분)")

    # Step 3: Publish
    publish_resp = requests.post(
        f"{GRAPH_BASE}/{ig_user_id}/media_publish",
        params={
            "access_token": access_token,
            "creation_id": container_id,
        },
        timeout=30,
    )
    if publish_resp.status_code != 200:
        raise Exception(f"Instagram Reels 발행 실패: {publish_resp.text}")

    media_id = publish_resp.json().get("id")
    print(f"OK [Instagram] Reels 업로드 완료! (media_id: {media_id})")

    return {
        "success": True,
        "media_id": media_id,
        "caption": caption,
        "platform": "instagram_reels",
    }


def disconnect(account_id: str | None = None) -> dict:
    _ensure_tokens_dir()
    if account_id:
        path = TOKENS_DIR / f"{account_id}.json"
        if path.exists():
            path.unlink()
        return {"success": True, "message": f"Instagram 계정 {account_id} 연동 해제"}
    for f in TOKENS_DIR.glob("*.json"):
        f.unlink()
    return {"success": True, "message": "모든 Instagram 연동이 해제되었습니다"}
