import os
import json
import time
import secrets
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly", "https://www.googleapis.com/auth/youtube"]
_BASE_DIR = Path(__file__).resolve().parent.parent.parent  # project root
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
        "containsSyntheticMedia": True,  # AI 생성/변경 콘텐츠 자동 선언
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

    # 재생목록 자동 추가
    try:
        playlist_id = add_to_playlist(video_id, title, tags or [], channel_id)
        if playlist_id:
            result["playlist_id"] = playlist_id
    except Exception as e:
        print(f"   [재생목록] 자동 추가 실패 (업로드는 성공): {e}")

    # 고정 댓글 — 같은 카테고리 과거 영상 링크
    try:
        comment_text = _build_related_comment(video_id, title, tags or [], channel_id, channel)
        if comment_text:
            _post_pinned_comment(video_id, comment_text, channel_id)
            result["pinned_comment"] = True
    except Exception as e:
        print(f"   [고정 댓글] 실패 (업로드는 성공): {e}")

    return result


# ── 재생목록 자동 분류 ──────────────────────────────────────────

# 채널별 재생목록 구조 (성과 데이터 기반 — 채널마다 다름)
CHANNEL_PLAYLISTS = {
    "askanything": {  # KO — 동물 ✅(1,832), 인체 ❌
        "심해/바다": "🌊 심해의 비밀",
        "우주/행성": "🌌 우주와 행성",
        "공룡/고생물": "🦕 공룡과 고생물",
        "지구/자연": "🌍 지구와 자연",
        "동물": "🐾 놀라운 동물",
        "역사": "📜 역사 반전",
        "기타": "🔬 놀라운 과학",
    },
    "wonderdrop": {  # EN — 동물 ✅(408), 인체 ❌(115)
        "심해/바다": "🌊 Deep Sea Secrets",
        "우주/행성": "🌌 Space & Planets",
        "공룡/고생물": "🦕 Dinosaurs & Fossils",
        "지구/자연": "🌍 Earth & Nature",
        "동물": "🐾 Amazing Animals",
        "역사": "📜 History Revealed",
        "기타": "🔬 Amazing Science",
    },
    "exploratodo": {  # ES-LATAM — 동물 ✅(799), 인체 ❌(342)
        "심해/바다": "🌊 Secretos del Mar",
        "우주/행성": "🌌 Espacio y Planetas",
        "공룡/고생물": "🦕 Dinosaurios y Fósiles",
        "지구/자연": "🌍 Tierra y Naturaleza",
        "동물": "🐾 Animales Increíbles",
        "역사": "📜 Historia Revelada",
        "기타": "🔬 Ciencia Increíble",
    },
    "prismtale": {  # ES-US — 동물 ❌(26), 인체 ✅(1,595)
        "심해/바다": "🌊 Secretos del Abismo",
        "우주/행성": "🌌 Misterios del Espacio",
        "공룡/고생물": "🦕 Criaturas Extintas",
        "지구/자연": "🌍 Secretos de la Tierra",
        "인체/심리": "🧠 Secretos del Cuerpo",
        "역사": "📜 Historia Oculta",
        "기타": "🔬 Ciencia Oculta",
    },
}

# 하위 호환 — 이전 코드에서 PLAYLIST_CATEGORIES 참조하는 곳 대응
PLAYLIST_CATEGORIES = {}

# 카테고리 감지 키워드 (title/tags에서 매칭)
_CATEGORY_KEYWORDS = {
    "우주/행성": ["planet", "star", "space", "행성", "별", "우주", "천문", "sun", "moon", "saturn", "jupiter", "venus", "mars", "sol", "luna", "estrella", "galaxia", "neptun", "plut", "asteroid", "comet", "소행성", "혜성", "meteor", "nebula", "galaxy", "은하"],
    "공룡/고생물": ["dinosaur", "공룡", "fossil", "rex", "dragon", "fósil", "dinosaurio", "stego", "trice", "ankylo", "megalodon", "extinct"],
    "심해/바다": ["ocean", "sea", "deep", "바다", "심해", "해구", "mar", "océano", "marina", "whale", "고래", "ballena", "trench"],
    "지구/자연": ["earth", "지구", "volcano", "지진", "tierra", "volcán", "earthquake", "magnetic", "자기장", "climate", "ice age"],
    "동물": ["animal", "동물", "shark", "상어", "tiburón", "penguin", "octopus", "문어", "pulpo", "crow", "까마귀", "ant", "spider"],
    "역사": ["history", "역사", "ancient", "roman", "viking", "egypt", "medieval", "고대", "historia", "antiguo"],
    "인체/심리": ["body", "brain", "heart", "뇌", "심장", "인체", "blood", "cuerpo", "cerebro", "lung", "폐", "bone"],
    "물리/화학": ["physics", "물리", "화학", "quantum", "atom", "energy", "gravity", "중력", "원자", "física", "química"],
}

_playlist_cache: dict[str, dict[str, str]] = {}  # channel_id → {category: playlist_id}
_PLAYLIST_CACHE_FILE = TOKENS_DIR / "playlist_map.json"


def _detect_category(title: str, tags: list[str] = None, channel: str = None) -> str:
    """제목+태그에서 카테고리 자동 감지. 채널에 해당 재생목록 없으면 '기타'."""
    text = (title + " " + " ".join(tags or [])).lower()
    ch_playlists = CHANNEL_PLAYLISTS.get(channel, {}) if channel else {}

    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            # 이 채널에 해당 재생목록이 있는지 확인
            if ch_playlists and category not in ch_playlists:
                continue  # 없으면 다음 카테고리 시도
            return category
    return "기타"


def _get_playlist_lang(channel: str) -> str:
    """채널별 언어."""
    lang_map = {"askanything": "ko", "wonderdrop": "en", "exploratodo": "es", "prismtale": "es"}
    return lang_map.get(channel, "en")


def _load_playlist_cache():
    """저장된 재생목록 ID 로드."""
    global _playlist_cache
    if _PLAYLIST_CACHE_FILE.exists():
        try:
            with open(_PLAYLIST_CACHE_FILE, "r") as f:
                _playlist_cache = json.load(f)
        except Exception:
            _playlist_cache = {}


def _save_playlist_cache():
    """재생목록 ID 저장."""
    TOKENS_DIR.mkdir(exist_ok=True)
    with open(_PLAYLIST_CACHE_FILE, "w") as f:
        json.dump(_playlist_cache, f, ensure_ascii=False, indent=2)


def ensure_playlists(channel_id: str, channel: str) -> dict[str, str]:
    """채널에 카테고리별 재생목록이 있는지 확인, 없으면 생성. {category: playlist_id} 반환."""
    _load_playlist_cache()
    cache_key = channel_id or channel

    # 채널별 재생목록 구조
    ch_playlists = CHANNEL_PLAYLISTS.get(channel, CHANNEL_PLAYLISTS.get("askanything", {}))

    if cache_key in _playlist_cache and len(_playlist_cache[cache_key]) >= len(ch_playlists):
        return _playlist_cache[cache_key]

    creds = _get_credentials(channel_id)
    if not creds:
        return {}

    youtube = build("youtube", "v3", credentials=creds)

    # 기존 재생목록 조회
    existing = {}
    try:
        resp = youtube.playlists().list(part="snippet", mine=True, maxResults=50).execute()
        for item in resp.get("items", []):
            existing[item["snippet"]["title"]] = item["id"]
    except Exception as e:
        print(f"[재생목록] 조회 실패: {e}")
        return {}

    result = _playlist_cache.get(cache_key, {})

    for category, playlist_name in ch_playlists.items():
        if category in result:
            continue
        if playlist_name in existing:
            result[category] = existing[playlist_name]
            print(f"[재생목록] 기존 발견: {playlist_name}")
        else:
            try:
                resp = youtube.playlists().insert(
                    part="snippet,status",
                    body={
                        "snippet": {"title": playlist_name, "description": f"{category} 관련 쇼츠 모음"},
                        "status": {"privacyStatus": "public"},
                    },
                ).execute()
                result[category] = resp["id"]
                print(f"[재생목록] 생성: {playlist_name} → {resp['id']}")
            except Exception as e:
                print(f"[재생목록] 생성 실패 ({playlist_name}): {e}")

    _playlist_cache[cache_key] = result
    _save_playlist_cache()
    return result


def add_to_playlist(video_id: str, title: str, tags: list[str],
                    channel_id: str = None, channel: str = None) -> str | None:
    """업로드된 영상을 카테고리에 맞는 재생목록에 자동 추가."""
    category = _detect_category(title, tags, channel)
    if not category:
        print(f"[재생목록] 카테고리 감지 실패: {title}")
        return None

    playlists = ensure_playlists(channel_id, channel)
    playlist_id = playlists.get(category)
    if not playlist_id:
        print(f"[재생목록] '{category}' 재생목록 없음")
        return None

    creds = _get_credentials(channel_id)
    if not creds:
        return None

    youtube = build("youtube", "v3", credentials=creds)
    try:
        # 중복 체크: 이미 재생목록에 있는지 확인
        existing = youtube.playlistItems().list(
            part="snippet", playlistId=playlist_id, maxResults=50,
        ).execute()
        existing_ids = {item["snippet"]["resourceId"]["videoId"]
                       for item in existing.get("items", [])}
        if video_id in existing_ids:
            print(f"[재생목록] 이미 존재 — 스킵: '{title}'")
            return playlist_id

        youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                },
            },
        ).execute()
        lang = _get_playlist_lang(channel)
        playlist_name = PLAYLIST_CATEGORIES[category].get(lang, category)
        print(f"OK [재생목록] '{title}' → {playlist_name}")
        return playlist_id
    except Exception as e:
        print(f"[재생목록] 추가 실패: {e}")
        return None


def classify_existing_videos(channel_id: str = None, channel: str = None) -> dict:
    """기존 업로드 영상들을 재생목록에 소급 분류."""
    creds = _get_credentials(channel_id)
    if not creds:
        return {"error": "인증 필요"}

    youtube = build("youtube", "v3", credentials=creds)
    playlists = ensure_playlists(channel_id, channel)

    # 내 채널 영상 조회
    videos = []
    try:
        # 내 채널 ID 가져오기
        ch_resp = youtube.channels().list(part="contentDetails", mine=True).execute()
        uploads_id = ch_resp["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

        next_page = None
        while True:
            resp = youtube.playlistItems().list(
                part="snippet", playlistId=uploads_id, maxResults=50, pageToken=next_page,
            ).execute()
            for item in resp.get("items", []):
                videos.append({
                    "video_id": item["snippet"]["resourceId"]["videoId"],
                    "title": item["snippet"]["title"],
                })
            next_page = resp.get("nextPageToken")
            if not next_page:
                break
    except Exception as e:
        return {"error": f"영상 조회 실패: {e}"}

    # 각 영상 분류
    classified = 0
    for v in videos:
        result = add_to_playlist(v["video_id"], v["title"], [], channel_id, channel)
        if result:
            classified += 1

    return {"success": True, "total": len(videos), "classified": classified}


def _build_related_comment(video_id: str, title: str, tags: list[str],
                           channel_id: str = None, channel: str = None) -> str | None:
    """같은 카테고리의 과거 영상 2-3개를 찾아 고정 댓글 텍스트 생성."""
    category = _detect_category(title, tags)
    if not category:
        return None

    creds = _get_credentials(channel_id)
    if not creds:
        return None

    youtube = build("youtube", "v3", credentials=creds)
    lang = _get_playlist_lang(channel)

    # 같은 재생목록에서 영상 가져오기
    playlists = ensure_playlists(channel_id, channel)
    playlist_id = playlists.get(category)
    if not playlist_id:
        return None

    try:
        resp = youtube.playlistItems().list(
            part="snippet", playlistId=playlist_id, maxResults=10,
        ).execute()

        related = []
        for item in resp.get("items", []):
            vid = item["snippet"]["resourceId"]["videoId"]
            if vid == video_id:
                continue  # 자기 자신 제외
            vtitle = item["snippet"]["title"]
            related.append({"title": vtitle, "url": f"https://youtube.com/shorts/{vid}"})

        if not related:
            return None

        # 최대 3개
        picks = related[:3]

        # 채널별 언어로 댓글 작성
        headers = {
            "ko": "🔥 이것도 봐!",
            "en": "🔥 Watch these too!",
            "es": "🔥 ¡Mira estos también!",
        }
        header = headers.get(lang, headers["en"])

        lines = [header]
        for p in picks:
            lines.append(f"👉 {p['title']}")
            lines.append(f"   {p['url']}")

        return "\n".join(lines)

    except Exception as e:
        print(f"[고정 댓글] 관련 영상 조회 실패: {e}")
        return None


def _post_pinned_comment(video_id: str, text: str, channel_id: str = None):
    """댓글 작성 + 고정."""
    creds = _get_credentials(channel_id)
    if not creds:
        return

    youtube = build("youtube", "v3", credentials=creds)

    # 댓글 작성
    resp = youtube.commentThreads().insert(
        part="snippet",
        body={
            "snippet": {
                "videoId": video_id,
                "topLevelComment": {
                    "snippet": {"textOriginal": text}
                },
            }
        },
    ).execute()

    comment_id = resp["snippet"]["topLevelComment"]["id"]

    # 댓글 고정
    try:
        youtube.comments().setModerationStatus(
            id=comment_id,
            moderationStatus="published",
        ).execute()
    except Exception:
        pass  # 고정은 실패해도 댓글은 남아있음

    print(f"OK [고정 댓글] 댓글 작성 완료 (관련 영상 링크 포함)")


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
