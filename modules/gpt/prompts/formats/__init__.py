"""포맷 유형별 프롬프트 주입."""

from __future__ import annotations

from .who_wins import FRAGMENT as _WHO_WINS
from .if_premise import FRAGMENT as _IF_PREMISE
from .emotional_sci import FRAGMENT as _EMOTIONAL_SCI
from .fact import FRAGMENT as _FACT

# format_type 키 → 프롬프트 딕셔너리
_FORMAT_MAP: dict[str, dict[str, str]] = {
    "WHO_WINS": _WHO_WINS,
    "IF": _IF_PREMISE,
    "EMOTIONAL_SCI": _EMOTIONAL_SCI,
    "FACT": _FACT,
}

# ES 변형 모두 "es" 키로 처리
_LANG_NORMALIZE = {
    "ko": "ko",
    "en": "en",
    "es": "es",
    "es_us": "es",
    "es_latam": "es",
}


def inject_format_prompt(system_prompt: str, format_type: str | None, lang: str) -> str:
    """포맷 유형 프롬프트를 시스템 프롬프트 뒤에 주입.

    Args:
        system_prompt: 기존 시스템 프롬프트
        format_type: WHO_WINS / IF / EMOTIONAL_SCI / FACT / None
        lang: ko / en / es

    Returns:
        포맷 프롬프트가 주입된 시스템 프롬프트
    """
    if not format_type:
        return system_prompt

    fmt = format_type.upper().strip()
    fragments = _FORMAT_MAP.get(fmt, {})
    if not fragments:
        return system_prompt

    lang_key = _LANG_NORMALIZE.get(lang, "en")
    fragment = fragments.get(lang_key, fragments.get("en", ""))
    if not fragment:
        return system_prompt

    return system_prompt + fragment


# ── 포맷별 컷 수 가이드 ──
FORMAT_CUT_GUIDE: dict[str, dict[str, int]] = {
    "WHO_WINS":      {"min": 9, "max": 11, "ideal": 11},
    "IF":            {"min": 9, "max": 11, "ideal": 10},
    "EMOTIONAL_SCI": {"min": 8, "max": 9,  "ideal": 8},
    "FACT":          {"min": 8, "max": 10, "ideal": 9},
}


def get_format_cut_override(format_type: str | None,
                            channel_min: int, channel_max: int) -> tuple[int, int]:
    """포맷별 컷 수 범위 반환. 포맷 없으면 채널 기본값 유지."""
    if not format_type:
        return channel_min, channel_max
    guide = FORMAT_CUT_GUIDE.get(format_type.upper(), {})
    if not guide:
        return channel_min, channel_max
    return guide.get("min", channel_min), guide.get("max", channel_max)


# ── 키워드 기반 포맷 자동 감지 (LLM 호출 없이 무비용) ──
_DETECT_KEYWORDS: dict[str, dict[str, list[str]]] = {
    "WHO_WINS": {
        "ko": ["vs", " 대 ", "대결", "누가 이", "더 강한", "싸우면"],
        "en": [" vs ", "versus", "who would win", "who wins", "stronger"],
        "es": [" vs ", "versus", "quién ganaría", "más fuerte", "batalla"],
    },
    "IF": {
        "ko": ["만약", "없어지면", "사라진다면", "없다면", "없으면"],
        "en": ["what if", "if there were no", "disappeared", "without"],
        "es": ["qué pasaría si", "y si", "sin", "desapareciera"],
    },
    "EMOTIONAL_SCI": {
        "ko": ["우리 몸", "뇌가", "심장", "감정", "눈물", "수면", "호르몬", "외로움", "불안", "공감"],
        "en": ["your body", "your brain", "tears", "sleep", "hormone", "loneliness", "anxiety", "empathy"],
        "es": ["tu cuerpo", "tu cerebro", "lágrimas", "sueño", "hormona", "soledad", "ansiedad", "empatía"],
    },
    "FACT": {
        "ko": ["사실", "진실", "알려지지", "아무도 모르", "비밀", "충격적", "실제로", "숨겨진"],
        "en": ["truth", "fact", "nobody knows", "secret", "shocking", "actually", "hidden"],
        "es": ["verdad", "dato", "nadie sabe", "secreto", "impactante", "en realidad", "oculto"],
    },
}


def detect_format_type(topic: str, lang: str = "ko") -> str | None:
    """토픽 키워드로 포맷 자동 감지. 매칭 없으면 None."""
    if not topic:
        return None
    text = topic.lower()
    lang_key = _LANG_NORMALIZE.get(lang, "en")
    for fmt, keywords_by_lang in _DETECT_KEYWORDS.items():
        keywords = keywords_by_lang.get(lang_key, keywords_by_lang.get("en", []))
        if any(kw in text for kw in keywords):
            return fmt
    return None
