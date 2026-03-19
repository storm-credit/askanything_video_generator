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


def get_safety_fallback_prompt(original_prompt: str, retry_count: int, topic: str = "") -> str:
    """
    안전 정책 위반 시 단계적 프롬프트 폴백.
    retry_count=0: 금지 키워드만 제거한 원본 프롬프트 반환
    retry_count>=1: 주제 키워드를 유지한 안전 프롬프트 반환
    topic: 영상 전체 주제 (fallback 시 맥락 유지용)
    """
    if retry_count == 0:
        cleaned = _BANNED_KEYWORDS.sub("", original_prompt)
        cleaned = re.sub(r'\s{2,}', ' ', cleaned).strip()
        if cleaned:
            return cleaned
    # 주제 컨텍스트 확보: topic 파라미터 > 원본 프롬프트 키워드
    topic_clean = _BANNED_KEYWORDS.sub("", topic).strip() if topic else ""
    words = _BANNED_KEYWORDS.sub("", original_prompt).split()
    prompt_hint = " ".join(w for w in words if len(w) > 2)[:120]
    # 주제가 있으면 주제 우선, 없으면 프롬프트 키워드
    context = f"about {topic_clean}. {prompt_hint}" if topic_clean else prompt_hint
    if not context.strip():
        context = "abstract artistic scene with vibrant colors"
    return (
        f"A safe, beautiful cinematic visualization {context}. "
        "Atmospheric lighting, detailed textures, peaceful scene."
    )
