from __future__ import annotations

import re

_EMOTION_TAG_PATTERN = re.compile(
    r"\[(SHOCK|WONDER|TENSION|REVEAL|URGENCY|DISBELIEF|IDENTITY|CALM|LOOP)\]",
    re.IGNORECASE,
)

_FORMAT_TAGS: dict[str, set[str]] = {
    "WHO_WINS": {"SHOCK", "REVEAL", "DISBELIEF", "IDENTITY"},
    "IF": {"SHOCK", "REVEAL", "URGENCY", "DISBELIEF"},
    "EMOTIONAL_SCI": {"WONDER", "REVEAL", "CALM"},
    "FACT": {"SHOCK", "REVEAL", "DISBELIEF"},
    "COUNTDOWN": {"SHOCK", "REVEAL", "URGENCY", "IDENTITY"},
    "SCALE": {"WONDER", "SHOCK", "REVEAL"},
    "PARADOX": {"DISBELIEF", "REVEAL", "SHOCK"},
    "MYSTERY": {"TENSION", "REVEAL", "DISBELIEF"},
}

_HIGH_MOTION_FORMATS = {"WHO_WINS", "IF", "COUNTDOWN", "SCALE", "MYSTERY", "PARADOX"}
_MOTION_KEYWORDS = (
    "vs",
    "versus",
    "split",
    "transform",
    "giant",
    "massive",
    "reveal",
    "top 1",
    "#1",
    "silhouette",
    "door",
)


def extract_emotion_tag(text: str) -> str | None:
    match = _EMOTION_TAG_PATTERN.search(text or "")
    return match.group(1).upper() if match else None


def pick_hero_indices(cuts_data: list[dict], format_type: str | None) -> list[int]:
    fmt = (format_type or "FACT").upper()
    format_tags = _FORMAT_TAGS.get(fmt, {"SHOCK", "REVEAL"})
    max_video = 2 if fmt in _HIGH_MOTION_FORMATS else 1
    scored: list[tuple[int, int]] = []

    for idx, cut in enumerate(cuts_data):
        desc = str(cut.get("description", cut.get("text", "")))
        emotion = extract_emotion_tag(desc)
        combined = f"{cut.get('script', '')} {cut.get('prompt', '')} {desc}".lower()
        score = 0

        if emotion in format_tags:
            score += 5
        if emotion in {"SHOCK", "REVEAL", "URGENCY", "DISBELIEF"}:
            score += 3
        if any(word in combined for word in _MOTION_KEYWORDS):
            score += 2
        if fmt == "COUNTDOWN" and idx >= max(0, len(cuts_data) - 3):
            score += 2

        scored.append((score, idx))

    return [
        idx
        for score, idx in sorted(scored, key=lambda item: (-item[0], item[1]))[:max_video]
        if score >= 5
    ]
