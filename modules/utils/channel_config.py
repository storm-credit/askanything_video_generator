"""채널-언어 매핑 및 프리셋 설정.

채널을 선택하면 언어, 목소리, TTS 속도, 플랫폼 등 기본값이 자동 적용됩니다.
사용자가 개별 항목을 오버라이드할 수 있습니다.
"""
import re

# 채널별 기본 프리셋
# voice_id: ElevenLabs 음성 ID (Eric=한국어, Adam=영어)
# upload_accounts: 플랫폼별 업로드 계정 매핑
#   youtube: youtube_tokens/{channel_id}.json의 채널 ID
#   tiktok:  tiktok_tokens/{open_id}.json의 open_id
#   instagram: instagram_tokens/{ig_user_id}.json의 IG user ID
#   값이 None이면 해당 플랫폼의 첫 번째 연동 계정 사용 (폴백)
CHANNEL_PRESETS: dict[str, dict] = {
    "askanything": {
        "language": "ko",
        "voice_id": "cjVigY5qzO86Huf0OWal",  # Eric (한국어 남성)
        "tts_speed": 1.3,  # 1.2→1.3 (시청자 피드백: 갑갑하다)
        "min_cuts": 8,
        "max_cuts": 10,  # 빠른 말 기준으로도 10컷 안에서 더 압축
        "target_duration": "28-34",  # 최근 피드백 반영: 한국어는 짧고 강하게
        # 포맷별 최적 컷 수 (tts_speed 1.3x 기준, 목표 28-34초)
        "format_cuts": {
            "WHO_WINS":      {"min": 11, "max": 11},  # quality gate requires the full 11-cut duel structure
            "IF":            {"min": 9,  "max": 10},
            "EMOTIONAL_SCI": {"min": 8,  "max": 8},
            "FACT":          {"min": 9,  "max": 10},
            "COUNTDOWN":     {"min": 8,  "max": 9},
            "SCALE":         {"min": 7,  "max": 9},
            "MYSTERY":       {"min": 8,  "max": 8},
            "PARADOX":       {"min": 8,  "max": 8},
        },
        "preferred_formats": ["IF", "PARADOX", "FACT", "MYSTERY", "SCALE", "WHO_WINS"],
        "blocked_formats": ["COUNTDOWN"],
        "voice_settings": {
            "stability": 0.35,
            "similarity_boost": 0.82,
            "style": 0.35,
            "use_speaker_boost": True,
        },  # ElevenLabs 전용 (현재 미사용 — Qwen3 운영)
        "bgm_theme": "random",
        "platforms": ["youtube"],
        "caption_size": 58,
        "caption_y": 50,
        "camera_style": "cinematic",
        "visual_style": "high contrast, rim lighting from below, single key light, deep shadow fill ratio 70:30, ultra detailed, vibrant colors, cinematic angle, bold composition, highly saturated",
        "tone": "궁금증 자극, 충격적 팩트, 한국식 친근한 반말. Loop: very strong — first and last lines should nearly mirror each other for obvious repetition",
        "forbidden_phrases": ["미쳤", "미친", "ㅋㅋ", "ㄹㅇ", "레전드", "개쩔", "ㅎㄷㄷ", "갓", "존맛", "킹받"],
        "upload_accounts": {
            "youtube": None,   # askanything0725@gmail.com → OAuth 연동 후 자동 매핑
            "tiktok": None,
            "instagram": None,
        },
    },
    "wonderdrop": {
        "language": "en",
        "voice_id": "pNInz6obpgDQGcFmaJgB",  # Adam (영어 남성)
        "tts_speed": 1.05,  # 1.20→1.05 (시청자 피드백: 너무 빠름)
        "min_cuts": 8,
        "max_cuts": 10,
        "target_duration": "30-36",  # 설명보다 압축감 우선
        # 포맷별 최적 컷 수 (tts_speed 1.05x 기준, 목표 30-36초)
        "format_cuts": {
            "WHO_WINS":      {"min": 11, "max": 11},
            "IF":            {"min": 9,  "max": 10},
            "EMOTIONAL_SCI": {"min": 8,  "max": 8},
            "FACT":          {"min": 8,  "max": 9},
            "COUNTDOWN":     {"min": 8,  "max": 9},
            "MYSTERY":       {"min": 8,  "max": 8},
            "SCALE":         {"min": 7,  "max": 8},
            "PARADOX":       {"min": 8,  "max": 8},
        },
        "preferred_formats": ["FACT", "PARADOX", "MYSTERY", "IF", "SCALE", "EMOTIONAL_SCI"],
        "blocked_formats": ["WHO_WINS", "COUNTDOWN"],
        "voice_settings": {
            "stability": 0.45,  # 0.65→0.45 (단조로움 제거, 감정 표현력↑)
            "similarity_boost": 0.85,
            "style": 0.3,  # 0.2→0.3 (약간의 스타일 추가)
            "use_speaker_boost": True,
        },
        "bgm_theme": "random",
        "platforms": ["youtube"],
        "caption_size": 54,
        "caption_y": 50,
        "camera_style": "cinematic",
        "visual_style": "cinematic, high contrast, dark background with bright subject, one strong accent color, dramatic rim lighting, ultra detailed, depth of field, lens flare, high realism",
        "tone": "confident authority narrator, compelling and clear, like revealing a secret the viewer needs to know. NOT calm/detached — engaged and forward-driving. Loop: natural callback — last line makes Cut 1 feel like the answer.",
        "forbidden_phrases": ["insane", "mind-blowing", "you won't believe", "literally dying", "no cap", "bro", "lowkey", "ngl"],
        "upload_accounts": {
            "youtube": None,
            "tiktok": None,
            "instagram": None,
        },
    },
    "exploratodo": {
        "language": "es",
        "voice_id": "onwK4e9ZLuTAKqWW03F9",  # Daniel (스페인어 남성)
        "tts_speed": 1.05,  # 1.20→1.05 (시청자 피드백: 너무 빠름)
        "min_cuts": 8,
        "max_cuts": 10,
        "target_duration": "30-36",  # 최근 피드백 반영: 더 빠르고 날렵하게
        # 포맷별 최적 컷 수 (tts_speed 1.05x 기준, 목표 30-36초)
        "format_cuts": {
            "WHO_WINS":      {"min": 11, "max": 11},
            "IF":            {"min": 9,  "max": 9},
            "EMOTIONAL_SCI": {"min": 8,  "max": 8},
            "FACT":          {"min": 9,  "max": 9},
            "PARADOX":       {"min": 8,  "max": 8},
            "SCALE":         {"min": 7,  "max": 8},
            "COUNTDOWN":     {"min": 8,  "max": 9},
            "MYSTERY":       {"min": 8,  "max": 8},
        },
        "preferred_formats": ["PARADOX", "FACT", "IF", "MYSTERY", "SCALE"],
        "blocked_formats": ["WHO_WINS", "COUNTDOWN"],
        "voice_settings": {
            "stability": 0.4,
            "similarity_boost": 0.82,
            "style": 0.3,  # 0.6→0.3 (과장 제거)
            "use_speaker_boost": True,
        },
        "bgm_theme": "random",
        "platforms": ["youtube"],
        "caption_size": 54,
        "caption_y": 50,
        "camera_style": "cinematic",
        "visual_style": "bright colors, vibrant, golden hour warm tones, high saturation +20%, teal-orange color grade, exaggerated, glowing effects, eye catching, dramatic, colorful",
        "tone": "energetic, curious, fast-paced, engaging, surprising, entertaining, quick rhythm. Loop: strong and direct — simple repetition, punchy endings that mirror the hook",
        "forbidden_phrases": ["no manches", "qué chido", "dale", "tío", "mola", "flipar", "brutal tío"],
        "upload_accounts": {
            "youtube": None,
            "tiktok": None,
            "instagram": None,
        },
    },
    "prismtale": {
        "language": "es",
        "voice_id": "onwK4e9ZLuTAKqWW03F9",  # Daniel (스페인어 남성 — 미국 히스패닉 타겟)
        "tts_speed": 1.05,  # 1.20→1.05 (시청자 피드백: 너무 빠름)
        "min_cuts": 8,
        "max_cuts": 10,
        "target_duration": "32-38",  # 몰입감은 유지하되 숏폼 압축감 복구
        # 포맷별 최적 컷 수 (tts_speed 1.05x 기준, 목표 32-38초)
        "format_cuts": {
            "WHO_WINS":      {"min": 11, "max": 11},
            "IF":            {"min": 9,  "max": 10},
            "EMOTIONAL_SCI": {"min": 8,  "max": 9},
            "FACT":          {"min": 9,  "max": 10},
            "MYSTERY":       {"min": 8,  "max": 8},
            "PARADOX":       {"min": 8,  "max": 8},
            "SCALE":         {"min": 7,  "max": 8},
            "COUNTDOWN":     {"min": 8,  "max": 9},
        },
        "preferred_formats": ["MYSTERY", "PARADOX", "FACT", "EMOTIONAL_SCI", "IF"],
        "blocked_formats": ["WHO_WINS", "COUNTDOWN"],
        "voice_settings": {
            "stability": 0.55,
            "similarity_boost": 0.85,
            "style": 0.25,  # 0.35→0.25
            "use_speaker_boost": True,
        },
        "bgm_theme": "random",
        "platforms": ["youtube"],
        "caption_size": 54,
        "caption_y": 50,
        "camera_style": "cinematic",
        "visual_style": "cinematic, single motivated practical light source, 80% frame in shadow, ultra detailed, high contrast focus, mysterious atmosphere, glowing elements, sharp subject, dark background",
        "tone": "neutral Spanish with US Hispanic feel, clear, intriguing, cinematic, controlled, slight emphasis on shocking words, avoid sounding playful. Loop: medium — reconnect naturally but more explicitly than English, less obvious than Latin",
        "keyword_tags": ["NASA", "Universe", "Science", "Brain", "Space", "Discovery"],
        "forbidden_phrases": ["no mames", "qué onda", "chévere", "bacano", "tío", "mola", "guay"],
        "upload_accounts": {
            "youtube": None,
            "tiktok": None,
            "instagram": None,
        },
    },
}

CHANNEL_TITLE_RULES: dict[str, str] = {
    "askanything": (
        "Title formula: one concrete subject + one impossible consequence or one direct curiosity question. "
        "Questions are welcome when they feel immediate and punchy. Avoid vague endings like 비밀/정체 alone."
    ),
    "wonderdrop": (
        "Title formula: one concrete subject + one declarative twist. Prefer a statement over a casual question. "
        "Keep it crisp, cinematic, and proof-like."
    ),
    "exploratodo": (
        "Title formula: exact object or place + one reversal or urgent curiosity gap. "
        "Fast LATAM click energy, but still concrete. Avoid generic misterio titles without a subject."
    ),
    "prismtale": (
        "Title formula: one hidden concrete object, place, or phenomenon + one ominous reveal. "
        "Prefer mystery declarations over playful questions. If using secreto/misterio, pair it with a concrete noun."
    ),
}

CHANNEL_HOOK_PROFILES: dict[str, str] = {
    "askanything": (
        "askanything = bold, punchy Korean curiosity hook. Strong questions are allowed and often preferred. "
        "Open fast, sound conversational, and make the first line instantly repeatable."
    ),
    "wonderdrop": (
        "wonderdrop = confident documentary opener. Prefer a calm declarative line over a casual question. "
        "The first line should feel like the reveal already started."
    ),
    "exploratodo": (
        "exploratodo = energetic LATAM opener. Fast, urgent, highly clickable. "
        "Concrete nouns first, then the twist. Formal academic openings are bad."
    ),
    "prismtale": (
        "prismtale = dark, cinematic mystery declaration. Ominous, precise, and intriguing. "
        "Prefer a hidden-truth line over a casual question."
    ),
}

CHANNEL_CUT1_VISUAL_RULES: dict[str, str] = {
    "askanything": (
        "Cut 1 visual anchor: one impossible scale anomaly or physical contradiction, one dominant hero subject, "
        "aggressive contrast, fast-read silhouette, no clutter."
    ),
    "wonderdrop": (
        "Cut 1 visual anchor: one hero object or creature, strong proof-like documentary composition, "
        "clean background separation, premium realism, no collage."
    ),
    "exploratodo": (
        "Cut 1 visual anchor: one concrete object or creature in a high-tension moment, vivid color split, "
        "instant danger or reversal, center-weighted focus."
    ),
    "prismtale": (
        "Cut 1 visual anchor: one hidden object, place, or silhouette clue inside darkness or fog, "
        "single practical light source, ominous negative space, no busy collage."
    ),
}

_TITLE_LABEL_RE = re.compile(r"^\s*(?:제목|title|titulo|título)\s*:\s*", re.IGNORECASE)
_HANGUL_RE = re.compile(r"[가-힣]")
_WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ0-9]+")
_GENERIC_TITLE_RE = {
    "ko": re.compile(r"^(?:그\s*)?(?:비밀|정체|이유|진실)$"),
    "en": re.compile(
        r"^(?:the\s+)?(?:secret|mystery|truth|reason)(?:\s+(?:behind|of|about|why))?$",
        re.IGNORECASE,
    ),
    "es": re.compile(
        r"^(?:el|la|los|las)?\s*(?:secreto|misterio|verdad|raz[oó]n)(?:\s+(?:de|del|detr[aá]s|sobre))?$",
        re.IGNORECASE,
    ),
}
_ENGLISH_START_RE = re.compile(r"^(?:what if|the secret|the mystery|the truth|why |how )\b", re.IGNORECASE)
_SPANISH_MARK_RE = re.compile(r"[¿¡]")
_FORBIDDEN_TITLE_CHARS_RE = re.compile(r"[\r\n#]")
_LATIN_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "behind", "by", "de", "del", "el", "en", "for",
    "from", "how", "if", "is", "la", "las", "los", "of", "on", "or", "que", "si", "the",
    "this", "to", "what", "why", "y",
}


def _clean_public_title(title: str | None) -> str:
    text = str(title or "").strip()
    text = _TITLE_LABEL_RE.sub("", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip(" \"'`*-")


def _public_title_word_count(title: str) -> int:
    return len(_WORD_RE.findall(title))


def _content_token_count(title: str) -> int:
    tokens = [token.lower() for token in _WORD_RE.findall(title)]
    return len([token for token in tokens if token not in _LATIN_STOPWORDS and len(token) > 1])


def get_channel_title_quality_errors(
    channel: str | None,
    title: str | None,
    format_type: str | None = None,
    *,
    strict: bool = False,
) -> list[str]:
    """채널별 공개 제목 품질 오류를 반환한다.

    strict=True는 Day 파일 저장을 막아야 하는 구조/언어 오류만 잡고,
    strict=False는 업로드 직전 fallback 선택용으로 더 예민하게 평가한다.
    """
    channel_name = str(channel or "").strip().lower()
    title_text = _clean_public_title(title)
    fmt = str(format_type or "").upper().strip()
    preset = get_channel_preset(channel_name) or {}
    lang = str(preset.get("language") or "").strip().lower()
    errors: list[str] = []

    if not title_text:
        return ["제목이 비어 있음"]
    if _FORBIDDEN_TITLE_CHARS_RE.search(title_text):
        errors.append("제목에 줄바꿈 또는 # 포함")
    if _TITLE_LABEL_RE.search(str(title or "")):
        errors.append("제목 필드 라벨이 제목 값에 섞임")

    if channel_name != "askanything" and _HANGUL_RE.search(title_text):
        errors.append("비한국 채널 제목에 한글 포함")
    if channel_name == "wonderdrop" and _SPANISH_MARK_RE.search(title_text):
        errors.append("wonderdrop 제목에 스페인어 문장부호 포함")
    if channel_name in {"exploratodo", "prismtale"} and _ENGLISH_START_RE.search(title_text):
        errors.append("스페인어 채널 제목이 영어식 제목으로 시작")

    generic_re = _GENERIC_TITLE_RE.get(lang)
    if generic_re and generic_re.match(title_text):
        errors.append("구체 명사 없는 generic 제목")

    lowered = title_text.lower()
    for phrase in preset.get("forbidden_phrases", []) or []:
        phrase_text = str(phrase).strip().lower()
        if phrase_text and phrase_text in lowered:
            errors.append(f"채널 금지 표현 포함: {phrase}")

    if strict:
        return errors

    if channel_name == "askanything":
        compact_len = len(re.sub(r"\s+", "", title_text))
        if compact_len > 18:
            errors.append("askanything 제목이 18자 초과")
    elif _public_title_word_count(title_text) > 10:
        errors.append(f"{channel_name} 제목이 10단어 초과")

    if channel_name == "wonderdrop":
        if title_text.endswith("?") and fmt != "IF":
            errors.append("wonderdrop은 IF 외 질문형보다 선언형 우선")
        if re.search(r"(?i)\b(?:who\s+wins|vs\.?|versus)\b", title_text):
            errors.append("wonderdrop 제목에 대결/vs 신호 포함")
        if lowered.startswith("what if") and fmt != "IF":
            errors.append("wonderdrop 제목이 What If로 시작")
    elif channel_name == "exploratodo":
        if re.search(r"(?i)\b(?:vs\.?|versus)\b", title_text):
            errors.append("exploratodo 제목에 대결/vs 신호 포함")
    elif channel_name == "prismtale":
        if re.search(r"(?i)\b(?:secreto|misterio)\b", title_text) and _content_token_count(title_text) < 2:
            errors.append("prismtale 미스터리 제목에 구체 명사 부족")

    if channel_name in {"wonderdrop", "exploratodo", "prismtale"} and _content_token_count(title_text) < 2:
        errors.append("제목에 구체 content token 부족")

    return errors


def choose_channel_upload_title(
    channel: str | None,
    metadata_title: str | None,
    preview_title: str | None,
    topic: str | None,
    format_type: str | None = None,
) -> tuple[str, list[str]]:
    """업로드 직전 채널별 제목 fallback을 선택한다."""
    candidates = [
        ("Day", _clean_public_title(metadata_title)),
        ("Preview", _clean_public_title(preview_title)),
        ("Topic", _clean_public_title(topic)),
    ]
    audit: list[str] = []
    day_errors: list[str] = []

    for source, candidate in candidates:
        if not candidate:
            continue
        errors = get_channel_title_quality_errors(channel, candidate, format_type, strict=False)
        if not errors:
            if source != "Day" and day_errors:
                audit.append(f"Day 제목 가드: {'; '.join(day_errors[:3])} -> {source} 제목 사용")
            return candidate, audit
        if source == "Day":
            day_errors = errors

    fallback = next((candidate for _, candidate in candidates if candidate), "")
    if day_errors:
        audit.append(f"Day 제목 가드 경고: {'; '.join(day_errors[:3])}")
    return fallback, audit

LEAD_CHANNEL_BY_FORMAT: dict[str, str] = {
    "IF": "askanything",
    "SCALE": "askanything",
    "WHO_WINS": "askanything",
    "FACT": "wonderdrop",
    "PARADOX": "exploratodo",
    "MYSTERY": "prismtale",
    "EMOTIONAL_SCI": "askanything",
}


def get_upload_account(channel: str | None, platform: str) -> str | None:
    """채널의 플랫폼별 업로드 계정 ID를 반환합니다.

    Returns:
        계정 ID (str) or None (첫 번째 연동 계정 폴백)
    """
    preset = get_channel_preset(channel)
    if not preset:
        return None
    accounts = preset.get("upload_accounts", {})
    return accounts.get(platform)


def get_channel_preset(channel: str | None) -> dict | None:
    """채널 프리셋 반환. 없으면 None."""
    if not channel:
        return None
    return CHANNEL_PRESETS.get(channel)


def normalize_format_for_channel(channel: str | None, format_type: str | None) -> tuple[str | None, str | None]:
    """채널별 금지 포맷을 안전한 선호 포맷으로 치환한다."""
    if not format_type:
        return None, None

    fmt = str(format_type).upper().strip()
    if not fmt:
        return None, None

    preset = get_channel_preset(channel) or {}
    blocked = {str(item).upper().strip() for item in preset.get("blocked_formats", [])}
    if fmt not in blocked:
        return fmt, None

    preferred = [
        str(item).upper().strip()
        for item in preset.get("preferred_formats", [])
        if str(item).upper().strip() not in blocked
    ]
    fallback = preferred[0] if preferred else "FACT"
    reason = f"채널 보호 규칙: {channel}에서 {fmt} 차단 → {fallback}"
    return fallback, reason


def get_channel_names() -> list[str]:
    """등록된 채널 이름 목록 반환."""
    return list(CHANNEL_PRESETS.keys())


def get_channel_title_rule(channel: str | None) -> str:
    """채널별 제목 공식 설명."""
    if not channel:
        return "Title formula: one concrete subject + one curiosity gap."
    return CHANNEL_TITLE_RULES.get(channel, "Title formula: one concrete subject + one curiosity gap.")


def get_channel_hook_profile(channel: str | None) -> str:
    """채널별 컷1 훅 성격 설명."""
    if not channel:
        return "default = short, strong, curiosity-driven opener."
    return CHANNEL_HOOK_PROFILES.get(channel, "default = short, strong, curiosity-driven opener.")


def get_channel_cut1_visual_rule(channel: str | None) -> str:
    """채널별 컷1 비주얼 앵커 설명."""
    if not channel:
        return "Cut 1 visual anchor: one dominant hero subject, high contrast, no clutter."
    return CHANNEL_CUT1_VISUAL_RULES.get(channel, "Cut 1 visual anchor: one dominant hero subject, high contrast, no clutter.")


def pick_lead_channel(format_type: str | None, available_channels: list[str] | tuple[str, ...] | set[str]) -> str | None:
    """포맷 기준 선행 배포 채널을 선택한다."""
    channels = [str(ch) for ch in available_channels if ch]
    if not channels:
        return None

    fmt = str(format_type or "FACT").upper().strip()
    preferred = LEAD_CHANNEL_BY_FORMAT.get(fmt)
    if preferred in channels:
        return preferred

    fallback_order = ["askanything", "wonderdrop", "exploratodo", "prismtale"]
    for channel in fallback_order:
        if channel in channels:
            return channel
    return channels[0]


# ── 채널별 업로드 계정 영속성 (JSON 파일) ──
import json
from pathlib import Path

_ACCOUNTS_FILE = Path("youtube_tokens/channel_accounts.json")


def set_upload_account(channel: str, platform: str, account_id: str | None):
    """채널의 업로드 계정을 설정하고 디스크에 저장합니다."""
    preset = CHANNEL_PRESETS.get(channel)
    if not preset:
        return
    if "upload_accounts" not in preset:
        preset["upload_accounts"] = {}
    preset["upload_accounts"][platform] = account_id
    _save_accounts()


def _save_accounts():
    """모든 채널의 upload_accounts를 JSON으로 저장합니다."""
    data = {}
    for name, preset in CHANNEL_PRESETS.items():
        accounts = preset.get("upload_accounts", {})
        # None이 아닌 값만 저장
        filtered = {k: v for k, v in accounts.items() if v is not None}
        if filtered:
            data[name] = filtered
    _ACCOUNTS_FILE.parent.mkdir(exist_ok=True)
    with open(_ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_accounts():
    """서버 시작 시 저장된 upload_accounts를 로드합니다."""
    if not _ACCOUNTS_FILE.exists():
        return
    try:
        with open(_ACCOUNTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        for name, accounts in data.items():
            if name in CHANNEL_PRESETS:
                if "upload_accounts" not in CHANNEL_PRESETS[name]:
                    CHANNEL_PRESETS[name]["upload_accounts"] = {}
                CHANNEL_PRESETS[name]["upload_accounts"].update(accounts)
        print(f"[채널 매핑] {len(data)}개 채널 업로드 계정 로드 완료")
    except Exception as e:
        print(f"[채널 매핑] 로드 실패: {e}")


# 모듈 로드 시 자동 로드
_load_accounts()


