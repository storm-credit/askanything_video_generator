"""채널-언어 매핑 및 프리셋 설정.

채널을 선택하면 언어, 목소리, TTS 속도, 플랫폼 등 기본값이 자동 적용됩니다.
사용자가 개별 항목을 오버라이드할 수 있습니다.
"""

# 채널별 기본 프리셋
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
        "caption_size": 58,
        "caption_y": 38,
        "visual_style": "cinematic dark, dramatic lighting, mystery vibe",
        "tone": "궁금증 자극, 충격적 팩트, 한국식 친근한 반말",
        "upload_accounts": {
            "youtube": None,   # askanything0725@gmail.com → OAuth 연동 후 자동 매핑
            "tiktok": None,
            "instagram": None,
        },
    },
    "wonderdrop": {
        "language": "en",
        "voice_id": "pNInz6obpgDQGcFmaJgB",  # Adam (영어 남성)
        "tts_speed": 0.9,
        "bgm_theme": "random",
        "platforms": ["youtube"],
        "caption_size": 54,
        "caption_y": 38,
        "visual_style": "bright, colorful, wonder-inspiring, nature-focused",
        "tone": "curious, wonder-filled, educational storytelling",
        "upload_accounts": {
            "youtube": None,
            "tiktok": None,
            "instagram": None,
        },
    },
    "exploratodo": {
        "language": "es",
        "voice_id": "onwK4e9ZLuTAKqWW03F9",  # Daniel (스페인어 남성)
        "tts_speed": 0.9,
        "bgm_theme": "random",
        "platforms": ["youtube"],
        "caption_size": 54,
        "caption_y": 38,
        "visual_style": "adventurous, vibrant, curiosity-driven, Latin-inspired",
        "tone": "curious, adventurous, engaging storytelling in Spanish",
        "upload_accounts": {
            "youtube": None,
            "tiktok": None,
            "instagram": None,
        },
    },
    "prismtale": {
        "language": "ko",
        "voice_id": "cjVigY5qzO86Huf0OWal",  # Eric (한국어 남성)
        "tts_speed": 0.85,
        "bgm_theme": "random",
        "platforms": ["youtube"],
        "caption_size": 58,
        "caption_y": 38,
        "visual_style": "dreamlike, prismatic colors, fantasy storytelling",
        "tone": "동화적, 신비로운 분위기, 한국식 친근한 반말",
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


# ── 채널별 업로드 계정 영속성 (JSON 파일) ──
import json
from pathlib import Path

_ACCOUNTS_FILE = Path("youtube_tokens/channel_accounts.json")


def set_upload_account(channel: str, platform: str, account_id: str | None):
    """채널의 업로드 계정을 설정하고 디스크에 저장합니다."""
    preset = CHANNEL_PRESETS.get(channel)
    if not preset:
        return
    if "upload_accounts" not in preset:
        preset["upload_accounts"] = {}
    preset["upload_accounts"][platform] = account_id
    _save_accounts()


def _save_accounts():
    """모든 채널의 upload_accounts를 JSON으로 저장합니다."""
    data = {}
    for name, preset in CHANNEL_PRESETS.items():
        accounts = preset.get("upload_accounts", {})
        # None이 아닌 값만 저장
        filtered = {k: v for k, v in accounts.items() if v is not None}
        if filtered:
            data[name] = filtered
    _ACCOUNTS_FILE.parent.mkdir(exist_ok=True)
    with open(_ACCOUNTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load_accounts():
    """서버 시작 시 저장된 upload_accounts를 로드합니다."""
    if not _ACCOUNTS_FILE.exists():
        return
    try:
        with open(_ACCOUNTS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        for name, accounts in data.items():
            if name in CHANNEL_PRESETS:
                if "upload_accounts" not in CHANNEL_PRESETS[name]:
                    CHANNEL_PRESETS[name]["upload_accounts"] = {}
                CHANNEL_PRESETS[name]["upload_accounts"].update(accounts)
        print(f"[채널 매핑] {len(data)}개 채널 업로드 계정 로드 완료")
    except Exception as e:
        print(f"[채널 매핑] 로드 실패: {e}")


# 모듈 로드 시 자동 로드
_load_accounts()


