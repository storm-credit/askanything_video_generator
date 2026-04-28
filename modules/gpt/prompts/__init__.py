"""시스템 프롬프트 로더.

인라인 900줄 프롬프트를 외부 파일로 분리하여 관리.
프롬프트 수정 시 코드를 건드리지 않아도 됨.
"""

from __future__ import annotations

import os
from functools import lru_cache

_PROMPTS_DIR = os.path.dirname(os.path.abspath(__file__))

# 언어 → 프롬프트 파일 매핑
_PROMPT_FILES = {
    "ko": "system_ko.txt",
    "en": "system_en.txt",
    "es_us": "system_es_us.txt",
    "es_latam": "system_es_latam.txt",
}


@lru_cache(maxsize=8)
def load_system_prompt(lang: str, channel: str | None = None) -> str:
    """언어/채널에 맞는 시스템 프롬프트를 파일에서 로드.
    캐시 무효화: load_system_prompt.cache_clear() 호출
    """
    if lang == "ko":
        key = "ko"
    elif lang == "en":
        key = "en"
    elif lang == "es":
        # 채널별 분기: 미국 히스패닉 vs 남미
        from modules.utils.channel_config import get_channel_preset
        preset = get_channel_preset(channel) if channel else None
        if preset and preset.get("keyword_tags"):
            key = "es_us"
        else:
            key = "es_latam"
    else:
        # 기타 언어: EN 프롬프트 + LANGUAGE OVERRIDE
        key = "en"

    filename = _PROMPT_FILES.get(key, "system_en.txt")
    filepath = os.path.join(_PROMPTS_DIR, filename)

    with open(filepath, encoding="utf-8") as f:
        prompt = f.read()

    # 기타 언어: 언어 오버라이드 추가
    if lang not in ("ko", "en", "es"):
        _LANG_NAMES = {
            "de": "German", "da": "Danish", "no": "Norwegian",
            "fr": "French", "pt": "Portuguese", "it": "Italian",
            "nl": "Dutch", "sv": "Swedish", "pl": "Polish",
            "ru": "Russian", "ja": "Japanese", "zh": "Chinese",
            "ar": "Arabic", "tr": "Turkish", "hi": "Hindi",
        }
        lang_name = _LANG_NAMES.get(lang, lang)
        prompt += f"""

[LANGUAGE OVERRIDE]
You MUST write ALL "script" fields and the "title" field in {lang_name}.
NEVER write scripts in English. All "script" fields MUST be in {lang_name} only.
The "image_prompt" and "description" fields must remain in English.
The narrator will speak in {lang_name}, so the script must be natural {lang_name}.
IMPORTANT: {lang_name} sentences tend to be longer than English. Keep each script to 7-11 words equivalent (~3-4 seconds) and avoid filler so the total video stays compact. Write 8-9 cuts by default unless channel override says otherwise.
"""

    return prompt


def inject_format_prompt(system_prompt: str, format_type: str | None, lang: str) -> str:
    """포맷 유형 프롬프트를 시스템 프롬프트 뒤에 주입."""
    from modules.gpt.prompts.formats import inject_format_prompt as _inject
    return _inject(system_prompt, format_type, lang)


def inject_channel_config(system_prompt: str, channel: str | None) -> str:
    """채널별 비주얼 스타일/톤/컷 수를 시스템 프롬프트에 주입.

    cutter.py의 lines 1171-1204 로직을 그대로 재현.
    """
    if not channel:
        return system_prompt

    from modules.utils.channel_config import get_channel_preset
    preset = get_channel_preset(channel)
    if not preset:
        return system_prompt

    visual_style = preset.get("visual_style", "")
    tone = preset.get("tone", "")
    if visual_style:
        system_prompt += f"""

[CHANNEL VISUAL IDENTITY]
All "image_prompt" fields MUST follow this visual style: {visual_style}
This is the channel's signature look — every image should feel cohesive with this aesthetic.
"""
    if tone:
        system_prompt += f"\n[NARRATOR TONE] {tone}\n"

    _min_c = preset.get("min_cuts", 8)
    _max_c = preset.get("max_cuts", 10)
    _dur = preset.get("target_duration", "35-45")
    system_prompt += f"""
[CHANNEL DURATION OVERRIDE]
This channel requires {_min_c}-{_max_c} cuts and {_dur} seconds total video duration.
This OVERRIDES any other cut/duration instructions above. Adjust words-per-cut accordingly.
"""

    keyword_tags = preset.get("keyword_tags", [])
    if keyword_tags:
        keywords_str = ", ".join(keyword_tags)
        system_prompt += f"""
[KEYWORD INJECTION]
Include these English keywords in the "tags" array (as hashtags): {keywords_str}
Also naturally weave 1-2 of these English terms into "image_prompt" fields where relevant (e.g. "NASA spacecraft", "human brain scan").
These English keywords help YouTube's algorithm classify this content for US audiences.
"""

    return system_prompt
