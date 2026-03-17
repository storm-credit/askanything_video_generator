"""이미지 생성 안전 정책 위반 시 프롬프트 폴백 로직 (DALL-E / Imagen 공용)."""

import re

# Safety filter: common banned/sensitive keywords to strip on first retry
_BANNED_KEYWORDS = re.compile(
    r'\b(blood|gore|violent|violence|weapon|gun|knife|dead|death|corpse|'
    r'nude|naked|sexual|drug|suicide|murder|kill|horror|gruesome|'
    r'terrorist|terrorism|explosion|bomb|torture|abuse)\b',
    re.IGNORECASE,
)


def is_safety_error(error_msg: str) -> bool:
    """안전 정책 위반 에러인지 판별."""
    lower = error_msg.lower()
    return any(kw in lower for kw in (
        "content_policy_violation", "safety", "blocked", "이미지가 없습니다",
    ))


def get_safety_fallback_prompt(original_prompt: str, retry_count: int) -> str:
    """
    안전 정책 위반 시 단계적 프롬프트 폴백.
    retry_count=0: 금지 키워드만 제거한 원본 프롬프트 반환
    retry_count>=1: 완전 안전한 제네릭 프롬프트 반환
    """
    if retry_count == 0:
        # First retry: strip banned keywords from original prompt
        cleaned = _BANNED_KEYWORDS.sub("", original_prompt)
        cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()
        if cleaned:
            return cleaned
        # If nothing left after filtering, fall through to generic
    # Second retry or empty after filter: safe prompt retaining more context
    # 원본에서 금지 키워드를 제거한 뒤 핵심 단어를 최대 15개 보존
    words = _BANNED_KEYWORDS.sub("", original_prompt).split()
    topic_hint = " ".join(w for w in words if len(w) > 2)[:150]  # 짧은 단어 제외, 150자 제한
    if not topic_hint:
        topic_hint = " ".join(original_prompt.split()[:6])
    return (
        f"A safe, beautiful cinematic visualization: {topic_hint}. "
        "Atmospheric lighting, detailed textures, peaceful scene, vertical 9:16 composition."
    )
