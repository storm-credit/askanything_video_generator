"""파이프라인 전역 공유 상수 및 유틸리티."""


# ── LLM 프로바이더 레이블 ──
PROVIDER_LABELS = {"gemini": "Gemini", "claude": "Claude", "openai": "ChatGPT"}


# ── National Geographic 마스터 스타일 프롬프트 (DALL-E / Imagen 공용) ──
MASTER_STYLE = (
    "Award-winning cinematic photograph, National Geographic high-end documentary style, "
    "hyper-detailed, global illumination, bright vibrant uplifting lighting, "
    "breathtaking aesthetic, 8K resolution, vertical composition, family-friendly. "
    "Absolutely NO TEXT, NO LETTERS, NO WORDS, NO WATERMARKS. "
)


def is_quota_error(err_str: str) -> bool:
    """429/503/쿼터 관련 에러인지 판별 (Imagen, Veo 공용)."""
    lower = err_str.lower()
    return any(kw in err_str for kw in ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE")) or \
           any(kw in lower for kw in ("quota", "rate_limit", "rate limit"))


def is_key_rotation_error(err_str: str) -> bool:
    """키 전환이 필요한 에러인지 판별 (쿼터 초과 + 유료 전용 + 권한 부족)."""
    if is_quota_error(err_str):
        return True
    lower = err_str.lower()
    return any(kw in lower for kw in ("paid plan", "upgrade your account", "not available on free", "billing"))
