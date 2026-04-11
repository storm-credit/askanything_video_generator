"""Voice selection logic — extracted from generate.py / prepare.py.

Single source of truth for voice maps, tone rules, and auto-selection.
"""

# ElevenLabs premade voice IDs
VOICE_MAP: dict[str, str] = {
    "eric":    "cjVigY5qzO86Huf0OWal",  # 차분/다큐
    "adam":    "pNInz6obpgDQGcFmaJgB",  # 깊은/권위
    "brian":   "nPczCjzI2devNBz1zQrb",  # 내레이션
    "bill":    "pqHfZKP75CvOlQylNhV4",  # 다큐/진지
    "daniel":  "onwK4e9ZLuTAKqWW03F9",  # 뉴스/정보
    "rachel":  "21m00Tcm4TlvDq8ikWAM",  # 차분/여성
    "sarah":   "EXAVITQu4vr4xnSDxMaL",  # 부드러운
    "matilda": "XrExE9yKIg1WjnnlVkGX",  # 따뜻한
    "charlie": "IKne3meq5aSn9XLyUdCD",  # 유머/캐주얼
    "antoni":  "ErXwobaYiN019PkySvjV",  # 만능
    "george":  "JBFqnCBsd6RMkjVDRZzb",  # 거친/공포
}

VOICE_ID_TO_NAME: dict[str, str] = {v: k.capitalize() for k, v in VOICE_MAP.items()}

# 주제 키워드 -> 최적 음성 매핑 (우선순위 순)
TONE_RULES: list[tuple[list[str], str]] = [
    # 공포/미스터리/범죄
    (["공포", "호러", "귀신", "유령", "살인", "미스터리", "괴담", "소름", "horror", "ghost", "murder", "creepy", "dark", "죽음", "저주", "심령", "폐허"], "george"),
    # 유머/재미/밈
    (["웃긴", "유머", "밈", "meme", "funny", "코미디", "개그", "ㅋㅋ", "레전드", "웃음", "드립", "짤"], "charlie"),
    # 과학/기술/교육
    (["과학", "기술", "AI", "인공지능", "우주", "NASA", "양자", "물리", "화학", "생물", "science", "tech", "quantum", "로봇", "컴퓨터", "프로그래밍"], "daniel"),
    # 역사/다큐
    (["역사", "전쟁", "고대", "조선", "제국", "세계대전", "history", "ancient", "war", "왕조", "문명", "유적"], "bill"),
    # 감성/힐링/동기부여
    (["감동", "힐링", "동기부여", "motivation", "inspiring", "감성", "위로", "희망", "사랑", "인생", "명언"], "matilda"),
    # 뉴스/시사/경제
    (["뉴스", "시사", "경제", "정치", "주식", "투자", "부동산", "금리", "인플레이션", "news", "economy", "stock", "비트코인", "코인"], "adam"),
    # 자연/동물/여행
    (["자연", "동물", "여행", "바다", "산", "nature", "animal", "travel", "풍경", "safari", "ocean"], "sarah"),
]


def auto_select_voice(topic: str, language: str = "ko") -> str:
    """주제 키워드를 분석하여 최적의 ElevenLabs 음성 ID를 반환합니다."""
    topic_lower = topic.lower()
    for keywords, voice_name in TONE_RULES:
        for kw in keywords:
            if kw.lower() in topic_lower:
                print(f"[음성 자동 선택] '{kw}' 매칭 → {voice_name} ({VOICE_MAP[voice_name][:12]}...)")
                return VOICE_MAP[voice_name]
    # 기본값: Eric (차분한 다큐 톤, 만능)
    return VOICE_MAP["eric"]


def voice_name(voice_id: str) -> str:
    """음성 ID를 이름으로 변환합니다."""
    return VOICE_ID_TO_NAME.get(voice_id, voice_id[:12] + "...")


def resolve_voice(voice_id_input: str | None, topic: str, language: str, channel: str | None) -> tuple[str | None, dict | None]:
    """Resolve final voice_id and voice_settings from user input + channel preset.

    Returns (voice_id, voice_settings).
    """
    from modules.utils.channel_config import get_channel_preset

    channel_voice_id = None
    channel_voice_settings = None

    if voice_id_input == "auto":
        channel_voice_id = auto_select_voice(topic, language)
    elif voice_id_input:
        channel_voice_id = voice_id_input

    if not channel_voice_id:
        preset = get_channel_preset(channel)
        if preset:
            channel_voice_id = preset.get("voice_id")
            channel_voice_settings = preset.get("voice_settings")
    else:
        preset = get_channel_preset(channel)
        if preset:
            channel_voice_settings = preset.get("voice_settings")

    return channel_voice_id, channel_voice_settings
