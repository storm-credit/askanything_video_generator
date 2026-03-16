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
    # Second retry or empty after filter: generic safe prompt
    topic_hint = " ".join(original_prompt.split()[:6])
    return (
        f"A safe, beautiful cinematic visualization related to: {topic_hint}. "
        "National Geographic documentary style, atmospheric lighting, "
        "bright and uplifting, vertical composition, NO TEXT, NO LETTERS."
    )
