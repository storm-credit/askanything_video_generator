"""채널-언어 매핑 및 프리셋 설정.

채널을 선택하면 언어, 목소리, TTS 속도, 플랫폼 등 기본값이 자동 적용됩니다.
사용자가 개별 항목을 오버라이드할 수 있습니다.
"""

# 채널별 기본 프리셋
# voice_id: ElevenLabs 음성 ID (Eric=한국어, Adam=영어)
CHANNEL_PRESETS: dict[str, dict] = {
    "askanything": {
        "language": "ko",
        "voice_id": "cjVigY5qzO86Huf0OWal",  # Eric (한국어 남성)
        "tts_speed": 0.85,
        "bgm_theme": "random",
        "platforms": ["youtube"],
        "caption_size": 48,
        "caption_y": 28,
        "visual_style": "cinematic dark, dramatic lighting, mystery vibe",
        "tone": "궁금증 자극, 충격적 팩트, 한국식 친근한 반말",
    },
    "wonderdrop": {
        "language": "en",
        "voice_id": "pNInz6obpgDQGcFmaJgB",  # Adam (영어 남성)
        "tts_speed": 0.9,
        "bgm_theme": "random",
        "platforms": ["youtube", "tiktok"],
        "caption_size": 44,
        "caption_y": 28,
        "visual_style": "bright, colorful, wonder-inspiring, nature-focused",
        "tone": "curious, wonder-filled, educational storytelling",
    },
}


def get_channel_preset(channel: str | None) -> dict | None:
    """채널 프리셋 반환. 없으면 None."""
    if not channel:
        return None
    return CHANNEL_PRESETS.get(channel)


def get_channel_names() -> list[str]:
    """등록된 채널 이름 목록 반환."""
    return list(CHANNEL_PRESETS.keys())


def apply_channel_defaults(channel: str | None, current: dict) -> dict:
    """채널 프리셋을 기본값으로 적용. 사용자가 명시적으로 설정한 값은 유지.

    current: 현재 설정값 (API 요청에서 받은 값)
    반환: 채널 기본값이 적용된 설정 dict
    """
    preset = get_channel_preset(channel)
    if not preset:
        return current

    result = dict(current)
    # 채널 프리셋의 각 키를 기본값으로 적용 (현재 값이 기본값이면 프리셋으로 대체)
    for key, default_val in preset.items():
        if key in result:
            result[key] = default_val

    return result
