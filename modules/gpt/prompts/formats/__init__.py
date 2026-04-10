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
