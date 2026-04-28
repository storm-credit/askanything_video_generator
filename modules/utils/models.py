"""
Google AI 모델 체인 설정

퀄리티 우선 전략:
  기본값은 Standard 모델 사용, 429 쿼터 초과 시에만 Fast 변형으로 자동 폴백.
  같은 API 키라도 모델별 RPM/RPD가 독립이므로 실질 한도가 2배.

환경변수 오버라이드:
  IMAGEN_MODEL, VEO_MODEL 등을 설정하면 체인이 비활성화되고 해당 모델만 사용.
"""

# Imagen 모델 체인: Standard → Fast → Ultra → (Nano Banana) → DALL-E
# Fast가 가성비 최적, Ultra는 무거운 폴백, Nano Banana는 imagen.py에서 별도 처리
IMAGEN_MODELS = [
    {"id": "imagen-4.0-generate-001", "tag": "standard", "label": "Imagen 4"},
    {"id": "imagen-4.0-fast-generate-001", "tag": "fast", "label": "Imagen 4 Fast"},
    {"id": "imagen-4.0-ultra-generate-001", "tag": "ultra", "label": "Imagen 4 Ultra"},
]
# Nano Banana는 별도 API 방식이라 imagen.py에서 직접 폴백 호출

# Veo 모델 체인:
#   - 일반 운영: Fast 우선 (비용/속도 최적화)
#   - hero-only: Standard 우선 (핵심 컷 품질 우선)
VEO_MODELS = [
    {"id": "veo-3.1-fast-generate-001", "tag": "fast", "label": "Veo 3.1 Fast"},
    {"id": "veo-3.1-generate-001", "tag": "standard", "label": "Veo 3.1"},
    {"id": "veo-3.0-fast-generate-001", "tag": "fast", "label": "Veo 3 Fast"},
    {"id": "veo-3.0-generate-001", "tag": "standard", "label": "Veo 3"},
]
VEO_MODELS_HERO = [
    {"id": "veo-3.1-generate-001", "tag": "standard", "label": "Veo 3.1"},
    {"id": "veo-3.1-fast-generate-001", "tag": "fast", "label": "Veo 3.1 Fast"},
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
    "imagen-3.0-generate-002": {"rpm": 10, "rpd": 100, "note": "무료"},
    # Veo
    "veo-3.1-generate-001": {"rpm": 50, "rpd": 0, "note": "Vertex fixed quota / pricing page 기준"},
    "veo-3.1-fast-generate-001": {"rpm": 50, "rpd": 0, "note": "Vertex fixed quota / pricing page 기준"},
    "veo-3.0-generate-001": {"rpm": 10, "rpd": 0, "note": "Vertex fixed quota"},
    "veo-3.0-fast-generate-001": {"rpm": 10, "rpd": 0, "note": "Vertex fixed quota"},
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


def get_model_label(service: str, model_id: str | None) -> str:
    """서비스/모델 ID를 사람이 읽기 쉬운 라벨로 변환."""
    raw = (model_id or "").strip()
    if not raw:
        return ""
    for chain in (get_model_chain(service), get_model_chain(service, profile="hero-only")):
        for model in chain:
            if model["id"] == raw:
                return model.get("label", raw)
    return raw


def describe_video_model(video_engine: str, video_model: str | None) -> str:
    """알림/로그용 비디오 모델 라벨."""
    engine = (video_engine or "").strip().lower()
    model = (video_model or "").strip()
    if not engine:
        return model or "-"
    if engine != "veo3":
        return model or engine
    if not model or model == "hero-only":
        chain = " -> ".join(model_meta["label"] for model_meta in get_model_chain("veo3", profile="hero-only"))
        return f"Hero-only ({chain})"
    return get_model_label("veo3", model)


def get_model_chain(service: str, profile: str | None = None) -> list[dict]:
    """서비스별 모델 폴백 순서 반환."""
    if service == "veo3" and profile == "hero-only":
        return VEO_MODELS_HERO
    return _CHAINS.get(service, [])


def get_service_tag(service: str, model_id: str) -> str:
    """모델 ID에 대응하는 서비스:태그 문자열 반환.
    예: get_service_tag("imagen", "imagen-4.0-generate-001") → "imagen:standard"
    """
    chains = [get_model_chain(service)]
    if service == "veo3":
        chains.append(get_model_chain(service, profile="hero-only"))
    for chain in chains:
        for model in chain:
            if model["id"] == model_id:
                return f"{service}:{model['tag']}"
    return service
