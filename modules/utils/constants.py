"""파이프라인 전역 공유 상수 및 유틸리티."""

import os

# ── LLM 프로바이더 레이블 ──
PROVIDER_LABELS = {"gemini": "Gemini", "claude": "Claude", "openai": "ChatGPT"}


# ── 마스터 스타일 프롬프트 (DALL-E / Imagen 공용, Imagen 프롬프트 가이드 기반) ──
MASTER_STYLE = (
    "Professional photograph, photorealistic, 4K HDR, highly detailed, "
    "sharp focus, controlled lighting, "
    "vertical 9:16 composition, "
    "family-friendly. "
    "NO TEXT, NO LETTERS, NO WORDS, NO WATERMARKS, NO LOGO, "
    "NO diagrams, NO infographic, NO cartoon, NO anime, NO illustration. "
)


def get_motion_style(prompt: str, description: str = "") -> str:
    """감정 태그 기반 모션 스타일 결정 (Veo/Kling/Sora 공용).

    감정 태그([SHOCK] 등)는 description에 포함됨. prompt도 폴백으로 검색.
    """
    tag_styles = {
        "[SHOCK]": "fast aggressive zoom-in, sudden dramatic camera angles, high-energy dynamic movement",
        "[WONDER]": "slow graceful 360-degree panning, gentle reveal through deep focus, dreamlike smooth tracking",
        "[TENSION]": "slow creeping approach, tightening frame, close focus on details, building pressure",
        "[CALM]": "very slow static wide shot, minimal subtle motion, peaceful ambient lighting",
        "[REVEAL]": "sudden camera shift to new perspective, dramatic 90-degree angle change, dynamic reframing",
    }
    search_text = f"{description} {prompt}"
    for tag, style in tag_styles.items():
        if tag in search_text:
            return style
    return "smooth cinematic camera movement"


def is_quota_error(err_str: str) -> bool:
    """429/503/쿼터 관련 에러인지 판별 (Imagen, Veo 공용)."""
    lower = err_str.lower()
    return any(kw in lower for kw in ("429", "503", "resource_exhausted", "unavailable", "quota", "rate_limit", "rate limit"))


def is_key_rotation_error(err_str: str) -> bool:
    """키 전환이 필요한 에러인지 판별 (쿼터 초과 + 유료 전용 + 권한 부족)."""
    if is_quota_error(err_str):
        return True
    lower = err_str.lower()
    return any(kw in lower for kw in ("paid plan", "upgrade your account", "not available on free", "billing"))
