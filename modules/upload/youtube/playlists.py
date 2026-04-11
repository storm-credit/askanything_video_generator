import json
from googleapiclient.discovery import build

from .auth import _get_credentials, TOKENS_DIR


# ── 재생목록 자동 분류 ──────────────────────────────────────────

# 채널별 재생목록 구조 (성과 데이터 기반 — 채널마다 다름)
CHANNEL_PLAYLISTS = {
    "askanything": {  # KO — 동물 ✅(1,832), 인체 ✅
        "심해/바다": "🌊 심해의 비밀",
        "우주/행성": "🌌 우주와 행성",
        "공룡/고생물": "🦕 공룡과 고생물",
        "지구/자연": "🌍 지구와 자연",
        "동물": "🐾 놀라운 동물",
        "인체/심리": "🧠 인체의 비밀",
        "역사": "📜 역사 반전",
        "기타": "🔬 놀라운 과학",
    },
    "wonderdrop": {  # EN — 동물 ✅(408), 인체 ✅
        "심해/바다": "🌊 Deep Sea Secrets",
        "우주/행성": "🌌 Space & Planets",
        "공룡/고생물": "🦕 Dinosaurs & Fossils",
        "지구/자연": "🌍 Earth & Nature",
        "동물": "🐾 Amazing Animals",
        "인체/심리": "🧠 Body & Mind",
        "역사": "📜 History Revealed",
        "기타": "🔬 Amazing Science",
    },
    "exploratodo": {  # ES-LATAM — 동물 ✅(799), 인체 ✅
        "심해/바다": "🌊 Secretos del Mar",
        "우주/행성": "🌌 Espacio y Planetas",
        "공룡/고생물": "🦕 Dinosaurios y Fósiles",
        "지구/자연": "🌍 Tierra y Naturaleza",
        "동물": "🐾 Animales Increíbles",
        "인체/심리": "🧠 Cuerpo y Mente",
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

# ── 포맷별 재생목록 (자동 생성) ──
FORMAT_PLAYLISTS: dict[str, dict[str, str]] = {
    "askanything": {
        "WHO_WINS": "⚔️ 대결 시리즈",
        "IF": "🌀 만약에 시리즈",
        "FACT": "🔍 충격 팩트",
        "EMOTIONAL_SCI": "✨ 감성 과학",
        "COUNTDOWN": "🏆 TOP 5 랭킹",
        "SCALE": "📏 스케일 비교",
        "MYSTERY": "🔮 미스터리",
        "PARADOX": "🔄 역설",
    },
    "wonderdrop": {
        "WHO_WINS": "⚔️ Battle Series",
        "IF": "🌀 What If Series",
        "FACT": "🔍 Shocking Facts",
        "EMOTIONAL_SCI": "✨ Emotional Science",
        "SCALE": "📏 Scale Comparison",
        "PARADOX": "🔄 Mind-Bending Paradox",
        "MYSTERY": "🔮 Unsolved Mysteries",
        "COUNTDOWN": "🏆 TOP 5 Ranking",
    },
    "exploratodo": {
        "WHO_WINS": "⚔️ Serie de Batallas",
        "IF": "🌀 ¿Y Si...?",
        "FACT": "🔍 Datos Impactantes",
        "EMOTIONAL_SCI": "✨ Ciencia Emocional",
        "SCALE": "📏 Comparación de Escala",
        "COUNTDOWN": "🏆 TOP 5 Ranking",
        "PARADOX": "🔄 Paradojas Mentales",
        "MYSTERY": "🔮 Misterios",
    },
    "prismtale": {
        "WHO_WINS": "⚔️ Serie de Batallas",
        "IF": "🌀 ¿Y Si...?",
        "FACT": "🔍 Datos Ocultos",
        "EMOTIONAL_SCI": "✨ Ciencia Emocional",
        "MYSTERY": "🔮 Misterios Sin Resolver",
        "PARADOX": "🔄 Paradojas Mentales",
        "COUNTDOWN": "🏆 TOP 5 Ranking",
        "SCALE": "📏 Comparación de Escala",
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


def _detect_category(title: str, tags: list[str] = None, channel: str = None,
                     format_type: str | None = None) -> str:
    """제목+태그에서 카테고리 자동 감지. 채널에 해당 재생목록 없으면 '기타'.

    format_type이 주어지고 해당 채널의 FORMAT_PLAYLISTS에 존재하면 format_type을 우선 반환.
    """
    ch_playlists = CHANNEL_PLAYLISTS.get(channel, {}) if channel else {}

    # 포맷 타입 우선 확인
    if format_type and channel:
        fmt = format_type.upper()
        if fmt in FORMAT_PLAYLISTS.get(channel, {}):
            return fmt

    text = (title + " " + " ".join(tags or [])).lower()

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


def _load_ext_playlist_cache() -> dict:
    """포맷/시리즈 재생목록 캐시 로드 (dict 반환)."""
    if _PLAYLIST_CACHE_FILE.exists():
        try:
            with open(_PLAYLIST_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_ext_playlist_cache(cache: dict):
    """포맷/시리즈 재생목록 캐시 저장."""
    TOKENS_DIR.mkdir(exist_ok=True)
    # 기존 글로벌 캐시와 병합해서 저장
    merged = {}
    if _PLAYLIST_CACHE_FILE.exists():
        try:
            with open(_PLAYLIST_CACHE_FILE, "r", encoding="utf-8") as f:
                merged = json.load(f)
        except Exception:
            pass
    merged.update(cache)
    with open(_PLAYLIST_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)


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
        playlist_name = CHANNEL_PLAYLISTS.get(channel, {}).get(category, category)
        print(f"OK [재생목록] '{title}' → {playlist_name}")
        return playlist_id
    except Exception as e:
        print(f"[재생목록] 추가 실패: {e}")
        return None


def add_to_format_playlist(video_id: str, format_type: str | None,
                           channel_id: str, channel: str = "") -> str | None:
    """포맷별 재생목록에 영상 추가. 없으면 자동 생성."""
    if not format_type or not channel:
        return None

    fmt = format_type.upper()
    channel_formats = FORMAT_PLAYLISTS.get(channel, {})
    playlist_title = channel_formats.get(fmt)
    if not playlist_title:
        return None

    try:
        creds = _get_credentials(channel_id)
        if not creds:
            return None
        youtube = build("youtube", "v3", credentials=creds)

        # 캐시에서 포맷 재생목록 ID 확인
        cache = _load_ext_playlist_cache()
        cache_key = f"{channel_id}_format"
        format_map = cache.get(cache_key, {})

        playlist_id = format_map.get(fmt)
        if not playlist_id:
            # 기존 재생목록 검색
            resp = youtube.playlists().list(part="snippet", mine=True, maxResults=50).execute()
            for item in resp.get("items", []):
                if item["snippet"]["title"] == playlist_title:
                    playlist_id = item["id"]
                    break

            # 없으면 새로 생성
            if not playlist_id:
                body = {
                    "snippet": {
                        "title": playlist_title,
                        "description": f"Auto-generated playlist for {fmt} format videos",
                    },
                    "status": {"privacyStatus": "public"},
                }
                resp = youtube.playlists().insert(part="snippet,status", body=body).execute()
                playlist_id = resp["id"]
                print(f"  ✅ 포맷 재생목록 생성: {playlist_title} ({playlist_id})")

            # 캐시 저장
            format_map[fmt] = playlist_id
            cache[cache_key] = format_map
            _save_ext_playlist_cache(cache)

        # 중복 확인
        existing = youtube.playlistItems().list(
            part="snippet", playlistId=playlist_id, maxResults=50
        ).execute()
        if any(item["snippet"]["resourceId"]["videoId"] == video_id
               for item in existing.get("items", [])):
            return playlist_id

        # 추가
        youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
        ).execute()
        print(f"  ✅ 포맷 재생목록 추가: {playlist_title} ← {video_id}")
        return playlist_id
    except Exception as e:
        print(f"  ⚠️ 포맷 재생목록 오류: {e}")
        return None


def add_to_series_playlist(video_id: str, series_id: str | None, series_title: str | None,
                           channel_id: str, channel: str = "") -> str | None:
    """시리즈별 재생목록에 영상 추가. 없으면 자동 생성."""
    if not series_title:
        return None

    try:
        creds = _get_credentials(channel_id)
        if not creds:
            return None
        youtube = build("youtube", "v3", credentials=creds)

        # 캐시에서 시리즈 재생목록 ID 확인
        cache = _load_ext_playlist_cache()
        cache_key = f"{channel_id}_series"
        series_map = cache.get(cache_key, {})

        # series_id가 None이면 series_title을 캐시 키로 사용
        series_cache_key = series_id if series_id else series_title

        playlist_id = series_map.get(series_cache_key)
        if not playlist_id:
            # 기존 재생목록 검색
            resp = youtube.playlists().list(part="snippet", mine=True, maxResults=50).execute()
            for item in resp.get("items", []):
                if item["snippet"]["title"] == series_title:
                    playlist_id = item["id"]
                    break

            # 없으면 새로 생성
            if not playlist_id:
                body = {
                    "snippet": {
                        "title": series_title,
                        "description": f"시리즈: {series_id or series_title}",
                    },
                    "status": {"privacyStatus": "public"},
                }
                resp = youtube.playlists().insert(part="snippet,status", body=body).execute()
                playlist_id = resp["id"]
                print(f"  ✅ 시리즈 재생목록 생성: {series_title} ({playlist_id})")

            # 캐시 저장
            series_map[series_cache_key] = playlist_id
            cache[cache_key] = series_map
            _save_ext_playlist_cache(cache)

        # 중복 확인
        existing = youtube.playlistItems().list(
            part="snippet", playlistId=playlist_id, maxResults=50
        ).execute()
        if any(item["snippet"]["resourceId"]["videoId"] == video_id
               for item in existing.get("items", [])):
            return playlist_id

        # 추가
        youtube.playlistItems().insert(
            part="snippet",
            body={
                "snippet": {
                    "playlistId": playlist_id,
                    "resourceId": {"kind": "youtube#video", "videoId": video_id},
                }
            },
        ).execute()
        print(f"  ✅ 시리즈 재생목록 추가: {series_title} ← {video_id}")
        return playlist_id
    except Exception as e:
        print(f"  ⚠️ 시리즈 재생목록 오류: {e}")
        return None


_QUOTA_DAILY_LIMIT = 10_000
_QUOTA_CLASSIFY_MAX = _QUOTA_DAILY_LIMIT // 2  # 일일 한도의 50%만 사용

def classify_existing_videos(channel_id: str = None, channel: str = None) -> dict:
    """기존 업로드 영상들을 재생목록에 소급 분류.

    YouTube API 쿼터 보호: 일일 한도(10,000 units)의 50%(5,000 units) 초과 시 중단.
    - channels.list: 1 unit
    - playlistItems.list: 1 unit/call
    - playlistItems.insert: 50 units/call
    """
    creds = _get_credentials(channel_id)
    if not creds:
        return {"error": "인증 필요"}

    youtube = build("youtube", "v3", credentials=creds)
    playlists = ensure_playlists(channel_id, channel)

    quota_used = 0

    # 내 채널 영상 조회
    videos = []
    try:
        ch_resp = youtube.channels().list(part="contentDetails", mine=True).execute()
        quota_used += 1
        uploads_id = ch_resp["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

        next_page = None
        while True:
            if quota_used >= _QUOTA_CLASSIFY_MAX:
                print(f"[재생목록] 쿼터 한도 도달 ({quota_used}/{_QUOTA_CLASSIFY_MAX}) — 영상 목록 조회 중단")
                break
            resp = youtube.playlistItems().list(
                part="snippet", playlistId=uploads_id, maxResults=50, pageToken=next_page,
            ).execute()
            quota_used += 1
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

    # 각 영상 분류 (playlistItems.list 1 + insert 50 = 영상당 최대 51 units)
    classified = 0
    skipped_quota = 0
    for v in videos:
        # insert 50 + list 1 = 51 units 예약
        if quota_used + 51 > _QUOTA_CLASSIFY_MAX:
            skipped_quota += 1
            print(f"[재생목록] 쿼터 한도 임박 ({quota_used}/{_QUOTA_CLASSIFY_MAX}) — '{v['title']}' 이후 중단")
            break
        result = add_to_playlist(v["video_id"], v["title"], [], channel_id, channel)
        # add_to_playlist 내부: list 1 + insert 50 = 최대 51 units
        quota_used += 51
        if result:
            classified += 1

    print(f"[재생목록] 완료 — 쿼터 사용: {quota_used}/{_QUOTA_CLASSIFY_MAX} units, 분류: {classified}, 스킵(쿼터): {skipped_quota}")
    return {"success": True, "total": len(videos), "classified": classified, "skipped_quota": skipped_quota, "quota_used": quota_used}
