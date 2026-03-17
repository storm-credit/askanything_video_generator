"""채널-언어 매핑, 비용 프리셋, 비주얼 스타일 설정.

채널을 선택하면 언어, 목소리, TTS 속도, 플랫폼 등 기본값이 자동 적용됩니다.
사용자가 개별 항목을 오버라이드할 수 있습니다.
"""

# ═══════════════════════ 비용 티어 프리셋 ═══════════════════════
# 각 티어는 파이프라인의 모든 API 선택을 일괄 제어합니다.
# free: 무료 API만 사용 ($0/영상)
# standard: 기본 유료 API ($0.3~0.5/영상)
# premium: 최고 품질 ($2~5/영상)
COST_TIERS: dict[str, dict] = {
    "free": {
        "label": "무료 (Free Tier Only)",
        "llm_provider": "gemini",
        "llm_model": "gemini-2.5-flash",        # 무료 500 RPD
        "image_engine": "imagen",
        "image_model": "imagen-4.0-fast-generate-001",  # 무료 100 RPD, 빠름
        "video_engine": "none",
        "tts_engine": "elevenlabs",              # 향후 chatterbox 로컬 대체 가능
        "whisper_model": "whisper-1",            # 향후 faster-whisper 로컬 대체 가능
        "estimated_cost": "$0 (API 무료 한도 내)",
    },
    "standard": {
        "label": "표준 (Standard)",
        "llm_provider": "gemini",
        "llm_model": "gemini-2.5-pro",           # Pro 기획 (free=Flash 대비 품질↑)
        "image_engine": "imagen",
        "image_model": "imagen-4.0-generate-001", # Standard 모델 (free=Fast 대비 품질↑)
        "video_engine": "none",
        "tts_engine": "elevenlabs",
        "whisper_model": "whisper-1",
        "estimated_cost": "$0.3~0.5/영상",
    },
    "premium": {
        "label": "프리미엄 (Premium)",
        "llm_provider": "gemini",
        "llm_model": "gemini-2.5-pro",           # 최고 품질 기획
        "image_engine": "imagen",
        "image_model": "imagen-4.0-generate-001",  # Standard 고품질
        "video_engine": "veo3",                  # AI 비디오 생성
        "tts_engine": "elevenlabs",
        "whisper_model": "whisper-1",
        "estimated_cost": "$2~5/영상",
    },
}


def get_cost_tier(tier: str | None) -> dict | None:
    """비용 티어 프리셋 반환. 없으면 None."""
    if not tier:
        return None
    return COST_TIERS.get(tier)


def get_cost_tier_names() -> list[str]:
    """등록된 비용 티어 이름 목록 반환."""
    return list(COST_TIERS.keys())


# ═══════════════════════ 채널별 MASTER_STYLE ═══════════════════════
# 채널마다 다른 비주얼 아이덴티티 (YouTube 중복 감지 방지)
CHANNEL_MASTER_STYLES: dict[str, str] = {
    "askanything": (
        "Cinematic photograph, dark mystery documentary style, "
        "dramatic chiaroscuro lighting, deep shadows, "
        "vertical 9:16 composition, "
        "family-friendly. NO TEXT, NO WATERMARKS. "
    ),
    "wonderdrop": (
        "Vibrant photograph, bright wonder-filled documentary style, "
        "warm golden-hour lighting, rich saturated colors, "
        "vertical 9:16 composition, "
        "family-friendly. NO TEXT, NO WATERMARKS. "
    ),
}

# 기본 MASTER_STYLE (채널 미지정 시)
DEFAULT_MASTER_STYLE = (
    "Cinematic photograph, National Geographic documentary style, "
    "detailed, vertical 9:16 composition, "
    "family-friendly. NO TEXT, NO WATERMARKS. "
)


def get_master_style(channel: str | None) -> str:
    """채널별 MASTER_STYLE 반환. 미지정 시 기본값."""
    if channel and channel in CHANNEL_MASTER_STYLES:
        return CHANNEL_MASTER_STYLES[channel]
    return DEFAULT_MASTER_STYLE


# ═══════════════════════ 채널별 내러티브 구조 ═══════════════════════
# 각 채널이 다른 스토리텔링 패턴 사용 (YouTube 템플릿 감지 방지)
CHANNEL_NARRATIVE_STYLES: dict[str, dict] = {
    "askanything": {
        "hook_type": "conclusion_first",  # 결론부터 던지기
        "hook_instruction_ko": "가장 충격적인 결론/팩트를 첫 문장에 던져라.",
        "hook_instruction_en": "Drop the most shocking conclusion/fact in the FIRST sentence.",
        "ending_style": "callback",  # 첫 훅 회수
    },
    "wonderdrop": {
        "hook_type": "mystery_question",  # 미스터리 질문
        "hook_instruction_ko": "가장 궁금증을 자극하는 현상/사실을 던져라. 답은 마지막에.",
        "hook_instruction_en": "Present the most curiosity-triggering phenomenon. Save the answer for the end.",
        "ending_style": "answer_reveal",  # 마지막에 답 공개
    },
}


def get_narrative_style(channel: str | None) -> dict | None:
    """채널별 내러티브 스타일 반환."""
    if not channel:
        return None
    return CHANNEL_NARRATIVE_STYLES.get(channel)


# ═══════════════════════ 채널 프리셋 ═══════════════════════
# voice_id: ElevenLabs 음성 ID (Eric=한국어, Adam=영어)
# upload_accounts: 플랫폼별 업로드 계정 매핑
#   youtube: youtube_tokens/{channel_id}.json의 채널 ID
#   tiktok:  tiktok_tokens/{open_id}.json의 open_id
#   instagram: instagram_tokens/{ig_user_id}.json의 IG user ID
#   값이 None이면 해당 플랫폼의 첫 번째 연동 계정 사용 (폴백)
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
        "caption_font_color": "#FFFFFF",
        "caption_stroke_color": "#000000",
        "upload_accounts": {
            "youtube": None,
            "tiktok": None,
            "instagram": None,
        },
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
        "caption_font_color": "#FFFDE7",
        "caption_stroke_color": "#1B5E20",
        "upload_accounts": {
            "youtube": None,
            "tiktok": None,
            "instagram": None,
        },
    },
}


def get_upload_account(channel: str | None, platform: str) -> str | None:
    """채널의 플랫폼별 업로드 계정 ID를 반환합니다.

    Returns:
        계정 ID (str) or None (첫 번째 연동 계정 폴백)
    """
    preset = get_channel_preset(channel)
    if not preset:
        return None
    accounts = preset.get("upload_accounts", {})
    return accounts.get(platform)


def get_channel_preset(channel: str | None) -> dict | None:
    """채널 프리셋 반환. 없으면 None."""
    if not channel:
        return None
    return CHANNEL_PRESETS.get(channel)


def get_channel_names() -> list[str]:
    """등록된 채널 이름 목록 반환."""
    return list(CHANNEL_PRESETS.keys())
