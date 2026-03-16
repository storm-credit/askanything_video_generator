"""
Google AI 모델 체인 설정

퀄리티 우선 전략:
  기본값은 Standard 모델 사용, 429 쿼터 초과 시에만 Fast 변형으로 자동 폴백.
  같은 API 키라도 모델별 RPM/RPD가 독립이므로 실질 한도가 2배.

환경변수 오버라이드:
  IMAGEN_MODEL, VEO_MODEL 등을 설정하면 체인이 비활성화되고 해당 모델만 사용.
"""

# Imagen 모델 체인: Standard (RPM 10) → Fast (RPM 10)
IMAGEN_MODELS = [
    {"id": "imagen-4.0-generate-001", "tag": "standard", "label": "Imagen 4"},
    {"id": "imagen-4.0-fast-generate-001", "tag": "fast", "label": "Imagen 4 Fast"},
]

# Veo 모델 체인: Standard (RPM 2) → Fast (RPM 2)
VEO_MODELS = [
    {"id": "veo-3.0-generate-001", "tag": "standard", "label": "Veo 3"},
    {"id": "veo-3.0-fast-generate-001", "tag": "fast", "label": "Veo 3 Fast"},
]

# 모델별 Rate Limit 참고 (Google AI Studio 무료 기준, 2026-03 기준)
MODEL_RATE_LIMITS = {
    # Gemini LLM
    "gemini-2.5-pro": {"rpm": 5, "rpd": 25, "note": "무료"},
    "gemini-2.5-flash": {"rpm": 10, "rpd": 500, "note": "무료"},
    "gemini-2.0-flash": {"rpm": 15, "rpd": 1500, "note": "무료"},
    # Imagen
    "imagen-4.0-generate-001": {"rpm": 10, "rpd": 100, "note": "무료"},
    "imagen-4.0-fast-generate-001": {"rpm": 10, "rpd": 100, "note": "무료"},
    # Veo
    "veo-3.0-generate-001": {"rpm": 2, "rpd": 6, "note": "무료"},
    "veo-3.0-fast-generate-001": {"rpm": 2, "rpd": 6, "note": "무료"},
    # OpenAI
    "gpt-4o": {"rpm": 500, "rpd": 10000, "note": "유료"},
    "gpt-4o-mini": {"rpm": 500, "rpd": 10000, "note": "유료"},
    "gpt-4.1": {"rpm": 500, "rpd": 10000, "note": "유료"},
    "gpt-4.1-mini": {"rpm": 500, "rpd": 10000, "note": "유료"},
    "dall-e-3": {"rpm": 7, "rpd": 700, "note": "유료 Tier1"},
    # Claude
    "claude-sonnet-4-20250514": {"rpm": 50, "rpd": 1000, "note": "유료"},
    "claude-opus-4-20250514": {"rpm": 20, "rpd": 200, "note": "유료"},
    "claude-haiku-4-5-20251001": {"rpm": 50, "rpd": 1000, "note": "유료"},
}

_CHAINS = {
    "imagen": IMAGEN_MODELS,
    "veo3": VEO_MODELS,
}


def get_model_chain(service: str) -> list[dict]:
    """서비스별 모델 폴백 순서 반환."""
    return _CHAINS.get(service, [])


def get_service_tag(service: str, model_id: str) -> str:
    """모델 ID에 대응하는 서비스:태그 문자열 반환.
    예: get_service_tag("imagen", "imagen-4.0-generate-001") → "imagen:standard"
    """
    for model in get_model_chain(service):
        if model["id"] == model_id:
            return f"{service}:{model['tag']}"
    return service
