import os
import json
import time
import secrets
import requests
from pathlib import Path

# TikTok Content Posting API
# Docs: https://developers.tiktok.com/doc/content-posting-api-get-started
CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "")
CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "")
REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI", "http://localhost:8003/api/tiktok/callback")
TOKENS_DIR = Path("tiktok_tokens")

SCOPES = "user.info.basic,video.publish,video.upload"

# CSRF state 저장 (인증 플로우 중 검증용)
_pending_states: dict[str, float] = {}


def _ensure_tokens_dir():
    TOKENS_DIR.mkdir(exist_ok=True)


def _get_token_path(user_id: str = "default") -> Path:
    return TOKENS_DIR / f"{user_id}.json"


def _load_token(user_id: str = "default") -> dict | None:
    _ensure_tokens_dir()
    path = _get_token_path(user_id)
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
        print(f"[TikTok] 토큰 로드 실패 ({path}): {e}")
        return None


def _save_token(token_data: dict, user_id: str = "default") -> None:
    _ensure_tokens_dir()
    path = _get_token_path(user_id)
    path.write_text(json.dumps(token_data, indent=2))


def _refresh_token(token_data: dict) -> dict | None:
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        return None
    try:
        resp = requests.post("https://open.tiktokapis.com/v2/oauth/token/", json={
            "client_key": CLIENT_KEY,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            new_token = {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token", refresh_token),
                "expires_at": time.time() + data.get("expires_in", 86400),
                "open_id": data.get("open_id", token_data.get("open_id", "default")),
            }
            _save_token(new_token, new_token["open_id"])
            return new_token
    except Exception as e:
        print(f"[TikTok] 토큰 갱신 실패: {e}")
    return None


def get_auth_status() -> dict:
    if not CLIENT_KEY or not CLIENT_SECRET:
        return {"connected": False, "reason": "TIKTOK_CLIENT_KEY/SECRET 환경 변수가 설정되지 않았습니다", "accounts": []}
    _ensure_tokens_dir()
    accounts = []
    for token_file in sorted(TOKENS_DIR.glob("*.json")):
        user_id = token_file.stem
        token = _load_token(user_id)
        accounts.append({
            "id": user_id,
            "connected": token is not None,
        })
    return {"connected": len(accounts) > 0 and any(a["connected"] for a in accounts), "accounts": accounts}


def create_auth_url() -> str:
    if not CLIENT_KEY:
        raise ValueError("TIKTOK_CLIENT_KEY 환경 변수가 필요합니다")
    state = secrets.token_urlsafe(16)
    # 만료 시간 포함 저장 (5분)
    _pending_states[state] = time.time() + 300
    # 만료된 state 정리
    now = time.time()
    expired = [s for s, exp in _pending_states.items() if exp < now]
    for s in expired:
        _pending_states.pop(s, None)

    url = (
        f"https://www.tiktok.com/v2/auth/authorize/"
        f"?client_key={CLIENT_KEY}"
        f"&scope={SCOPES}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&state={state}"
    )
    return url


def handle_auth_callback(code: str, state: str | None = None) -> dict:
    # CSRF state 검증
    if state:
        expires_at = _pending_states.pop(state, None)
        if expires_at is None or time.time() > expires_at:
            raise ValueError("인증 state가 유효하지 않습니다. 다시 시도해주세요.")

    resp = requests.post("https://open.tiktokapis.com/v2/oauth/token/", json={
        "client_key": CLIENT_KEY,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
    }, timeout=15)

    if resp.status_code != 200:
        raise Exception(f"TikTok 토큰 교환 실패: {resp.text}")

    data = resp.json()
    open_id = data.get("open_id", "default")
    token_data = {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token", ""),
        "expires_at": time.time() + data.get("expires_in", 86400),
        "open_id": open_id,
    }
    _save_token(token_data, open_id)
    return {"success": True, "message": f"TikTok 계정 연동 완료 (ID: {open_id})"}


def upload_video(
    video_path: str,
    title: str,
    privacy_level: str = "SELF_ONLY",
    user_id: str | None = None,
) -> dict:
    """TikTok에 동영상을 업로드합니다.

    privacy_level: SELF_ONLY | MUTUAL_FOLLOW_FRIENDS | FOLLOWER_OF_CREATOR | PUBLIC_TO_EVERYONE
    """
    token = _load_token(user_id or "default")
    if not token:
        raise PermissionError("TikTok 인증이 필요합니다. 먼저 계정을 연동해주세요.")

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"동영상 파일을 찾을 수 없습니다: {video_path}")

    access_token = token["access_token"]
    file_size = os.path.getsize(video_path)

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }

    # Step 1: Initialize upload
    init_resp = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/inbox/video/init/",
        headers=headers,
        json={
            "source_info": {
                "source": "FILE_UPLOAD",
                "video_size": file_size,
                "chunk_size": file_size,
                "total_chunk_count": 1,
            },
        },
        timeout=30,
    )

    if init_resp.status_code != 200:
        raise Exception(f"TikTok 업로드 초기화 실패: {init_resp.text}")

    init_data = init_resp.json().get("data", {})
    publish_id = init_data.get("publish_id")
    upload_url = init_data.get("upload_url")

    if not upload_url:
        raise Exception(f"TikTok 업로드 URL을 받지 못했습니다: {init_resp.text}")

    # Step 2: Upload video file
    print(f"-> [TikTok] 업로드 시작: {title}")
    with open(video_path, "rb") as f:
        upload_headers = {
            "Content-Range": f"bytes 0-{file_size - 1}/{file_size}",
            "Content-Type": "video/mp4",
        }
        upload_resp = requests.put(upload_url, headers=upload_headers, data=f, timeout=300)

    if upload_resp.status_code not in (200, 201):
        raise Exception(f"TikTok 파일 업로드 실패: {upload_resp.status_code}")

    # Step 3: Publish
    publish_resp = requests.post(
        "https://open.tiktokapis.com/v2/post/publish/video/init/",
        headers=headers,
        json={
            "post_info": {
                "title": title[:150],
                "privacy_level": privacy_level,
                "disable_duet": False,
                "disable_comment": False,
                "disable_stitch": False,
            },
            "source_info": {
                "source": "PULL_FROM_URL",
                "video_url": upload_url,
            },
        },
        timeout=30,
    )

    if publish_resp.status_code != 200:
        print(f"[TikTok] 발행 경고: {publish_resp.status_code} {publish_resp.text[:200]}")

    print(f"OK [TikTok] 업로드 완료!")
    return {
        "success": True,
        "publish_id": publish_id,
        "title": title,
        "privacy": privacy_level,
    }


def disconnect(user_id: str | None = None) -> dict:
    _ensure_tokens_dir()
    if user_id:
        path = _get_token_path(user_id)
        if path.exists():
            path.unlink()
        return {"success": True, "message": f"TikTok 계정 {user_id} 연동 해제"}
    for f in TOKENS_DIR.glob("*.json"):
        f.unlink()
    return {"success": True, "message": "모든 TikTok 연동이 해제되었습니다"}
