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
