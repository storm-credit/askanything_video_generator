"""파이프라인 전역 공유 상수 및 유틸리티."""

import os
import re

# ── LLM 프로바이더 레이블 ──
PROVIDER_LABELS = {"gemini": "Gemini", "claude": "Claude", "openai": "ChatGPT"}


# ── 마스터 스타일 프롬프트 (DALL-E / Imagen 공용, Imagen 프롬프트 가이드 기반) ──
MASTER_STYLE = (
    "Professional photograph, photorealistic, cinematic quality, highly detailed, "
    "sharp focus, controlled lighting, "
    "vertical 9:16 composition, "
    "family-friendly. "
    "NO TEXT, NO LETTERS, NO WORDS, NO WATERMARKS, NO LOGO, "
    "NO diagrams, NO infographic, NO cartoon, NO anime, NO illustration. "
)


_TAG_STYLES = {
    "[SHOCK]": "fast aggressive push-in, sudden reframing, impact-first camera energy",
    "[WONDER]": "slow graceful orbit, deep-focus reveal, dreamlike floating camera",
    "[TENSION]": "slow creeping approach, tightening frame, pressure-building focus shifts",
    "[CALM]": "very slow wide hold, minimal subtle motion, serene ambient drift",
    "[REVEAL]": "sudden perspective shift, dramatic angle change, clean visual reveal beat",
    "[URGENCY]": "urgent forward drive, escalating handheld pressure, time-sensitive momentum",
    "[DISBELIEF]": "double-take reframing, abrupt pause then push-in, impossible moment emphasis",
    "[IDENTITY]": "heroic subject-centered framing, deliberate face-off composition, iconic presence",
    "[LOOP]": "circular return motion, mirrored camera echo, seamless loop-friendly ending beat",
}

_FORMAT_MOTION_BASE = {
    "WHO_WINS": "face-off staging, collision-ready blocking, one decisive confrontation beat",
    "IF": "transformation-first motion, before-and-after escalation, one impossible causal shift",
    "EMOTIONAL_SCI": "gentle wonder-led motion, intimate macro reveal, emotionally resonant pacing",
    "FACT": "documentary realism, grounded motion, one clean authoritative reveal",
    "COUNTDOWN": "rank escalation, spotlight reveal, one strongest payoff beat",
    "SCALE": "extreme size contrast, dramatic zoom-out or parallax, overwhelming sense of magnitude",
    "PARADOX": "truth-reversal motion, perspective flip, visual contradiction resolving into clarity",
    "MYSTERY": "foggy reveal, silhouette emergence, hidden-truth atmosphere with one discovery beat",
}

_CAMERA_STYLE_MODIFIERS = {
    "dynamic": "dynamic camera language, bold movement, strong momentum",
    "gentle": "gentle controlled motion, soft easing, elegant camera flow",
    "static": "mostly locked camera, minimal motion, movement reserved for the reveal moment",
    "cinematic": "cinematic composition, premium lens feel, dramatic but clean camera grammar",
}


def _extract_primary_emotion_tag(text: str) -> str | None:
    match = re.search(
        r"\[(SHOCK|WONDER|TENSION|REVEAL|URGENCY|DISBELIEF|IDENTITY|CALM|LOOP)\]",
        text or "",
        re.IGNORECASE,
    )
    return f"[{match.group(1).upper()}]" if match else None


def get_motion_style(
    prompt: str,
    description: str = "",
    format_type: str | None = None,
    camera_style: str = "auto",
) -> str:
    """감정/포맷/카메라 스타일을 합쳐 영상용 모션 스타일을 만든다."""
    search_text = f"{description} {prompt}"
    emotion_tag = _extract_primary_emotion_tag(search_text)
    fmt = (format_type or "").upper().strip()

    parts: list[str] = []
    if emotion_tag and fmt in _FORMAT_MOTION_BASE:
        parts.append(_FORMAT_MOTION_BASE[fmt])
    if emotion_tag and emotion_tag in _TAG_STYLES:
        parts.append(_TAG_STYLES[emotion_tag])

    normalized_camera = (camera_style or "auto").strip().lower()
    if normalized_camera != "auto":
        parts.append(_CAMERA_STYLE_MODIFIERS.get(normalized_camera, _CAMERA_STYLE_MODIFIERS["dynamic"]))

    if not parts:
        return "smooth cinematic camera movement with one memorable motion beat"
    return ", ".join(parts)


def build_video_generation_prompt(
    prompt: str,
    description: str = "",
    format_type: str | None = None,
    camera_style: str = "auto",
) -> str:
    """이미지 설명과 분리된 영상용 프롬프트를 조합한다."""
    motion = get_motion_style(
        prompt,
        description=description,
        format_type=format_type,
        camera_style=camera_style,
    )
    return (
        f"{motion}, 4K cinematic quality, one decisive memorable motion beat, "
        f"preserve the exact subject and scene from the image, no text, no logo. {prompt}"
    )


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
