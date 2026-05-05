"""WHO_WINS series continuity state.

Stores the next matchup teased by the final cut so the topic planner can
continue a VS series instead of treating it as a one-off video.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SERIES_DIR = Path(os.getenv("SERIES_STATE_DIR", os.path.join("data", "series")))

_DIRECT_VS_RE = re.compile(
    r"(?P<a>[0-9A-Za-z가-힣À-ÿ·'’\-\s]{1,48}?)\s+"
    r"(?:vs\.?|versus|contra)\s+"
    r"(?P<b>[0-9A-Za-z가-힣À-ÿ·'’\-\s]{1,48})",
    re.IGNORECASE,
)
_KO_MATCHUP_RE = re.compile(
    r"(?P<a>[0-9A-Za-z가-힣·'’\-\s]{1,36}?)\s*"
    r"(?:이랑|랑|하고|와|과| 대 )\s*"
    r"(?P<b>[0-9A-Za-z가-힣·'’\-\s]{1,36}?)"
    r"(?:가|이|은|는|을|를)?\s*"
    r"(?:붙|싸우|대결|맞붙|만나|겨루|누가|이길|승부)",
)
_NEXT_SIGNAL_RE = re.compile(
    r"다음|다음엔|다음에는|다음 편|다음 상대|도전자|next|pr[oó]xim|siguiente",
    re.IGNORECASE,
)
_KOREAN_PARTICLE_SUFFIX_RE = re.compile(r"(?:가|이|은|는|을|를|와|과|랑|이랑|하고)$")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_slug(text: str) -> str:
    slug = re.sub(r"[^\w가-힣.-]+", "-", text.strip(), flags=re.UNICODE).strip("-")
    return slug or "vs-series"


def _series_path(series_title: str) -> Path:
    return SERIES_DIR / f"{_safe_slug(series_title)}.json"


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def _load_series(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _iter_cuts(cuts: Any) -> list[dict[str, Any]]:
    if isinstance(cuts, dict):
        cuts = cuts.get("cuts") or []
    if not isinstance(cuts, list):
        return []
    return [cut for cut in cuts if isinstance(cut, dict)]


def _cut_text(cut: dict[str, Any]) -> str:
    parts = [
        str(cut.get("script") or ""),
        str(cut.get("text") or ""),
        str(cut.get("description") or ""),
        str(cut.get("topic") or ""),
    ]
    return " ".join(part.strip() for part in parts if part.strip())


def _clean_entity(value: str) -> str:
    text = re.sub(r"\[[^\]]+\]", " ", value or "")
    text = re.sub(
        r"^(?:다음(?:엔|에는|은)?|다음\s*상대(?:는|가)?|다음\s*도전자(?:는|가)?|"
        r"이번엔|그럼|예고|next|the next|next challenger|next episode|then)\s*[:：,]?\s*",
        "",
        text.strip(),
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\s*(?:진짜|정말|과연|붙으면|싸우면|대결하면|누가|누구|이길까|이길까\?|"
        r"wins?|who wins|would win|ganar[ií]a|gana|se enfrentan).*$",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"[\"'“”‘’`]+", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ,.:;!?¿¡()[]{}")
    previous = None
    while previous != text:
        previous = text
        text = _KOREAN_PARTICLE_SUFFIX_RE.sub("", text).strip()
    return text.strip()


def _format_matchup(left: str, right: str) -> str | None:
    left = _clean_entity(left)
    right = _clean_entity(right)
    if not left or not right:
        return None
    if left == right:
        return None
    return f"{left} vs {right}"


def extract_matchup(text: str) -> str | None:
    """Extract an A vs B matchup from a title or sentence."""
    if not text:
        return None

    direct = _DIRECT_VS_RE.search(text)
    if direct:
        matchup = _format_matchup(direct.group("a"), direct.group("b"))
        if matchup:
            return matchup

    korean = _KO_MATCHUP_RE.search(text)
    if korean:
        matchup = _format_matchup(korean.group("a"), korean.group("b"))
        if matchup:
            return matchup
    return None


def extract_next_matchup_from_cuts(cuts: Any) -> str | None:
    """Read the final-cut teaser and return the next matchup."""
    cut_items = _iter_cuts(cuts)
    if not cut_items:
        return None

    priority_texts: list[str] = []
    fallback_texts: list[str] = []
    for cut in reversed(cut_items[-3:]):
        text = _cut_text(cut)
        if not text:
            continue
        if _NEXT_SIGNAL_RE.search(text):
            priority_texts.append(text)
        fallback_texts.append(text)

    for text in [*priority_texts, *fallback_texts]:
        matchup = extract_matchup(text)
        if matchup:
            return matchup
    return None


def _split_matchup(matchup: str | None) -> tuple[str | None, str | None]:
    if not matchup:
        return None, None
    parts = re.split(r"\s+vs\.?\s+", matchup, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        return None, None
    return _clean_entity(parts[0]), _clean_entity(parts[1])


def extract_winner_from_cuts(cuts: Any, matchup: str | None = None) -> str | None:
    """Best-effort winner extraction from late WHO_WINS cuts."""
    cut_items = _iter_cuts(cuts)
    if not cut_items:
        return None
    late_text = " ".join(_cut_text(cut) for cut in cut_items[-4:])
    left, right = _split_matchup(matchup)
    winner_zone = ""
    marker = re.search(r"(?:승자(?:는|가)?|승리는|winner(?: is)?|gana|ganador(?: es)?)", late_text, re.IGNORECASE)
    if marker:
        winner_zone = late_text[marker.start(): marker.start() + 160]

    for side in [left, right]:
        if side and winner_zone and side in winner_zone:
            return side
    for side in [left, right]:
        if side and side in late_text and re.search(r"승자|승리|winner|gana|ganador", late_text, re.IGNORECASE):
            return side

    patterns = [
        r"승자(?:는|가)?\s*[,:\s]\s*(?P<winner>[^.?!,，]{1,40})",
        r"(?P<winner>[^.?!,，]{1,40})의\s+승리",
        r"winner(?: is)?\s+(?P<winner>[^.?!,，]{1,40})",
        r"gana\s+(?P<winner>[^.?!,，]{1,40})",
    ]
    for pattern in patterns:
        match = re.search(pattern, late_text, re.IGNORECASE)
        if match:
            winner = _clean_entity(match.group("winner"))
            if winner:
                return winner
    return None


def infer_series_title(topic: str, title: str = "", series_title: str | None = None) -> str:
    """Infer the correct VS series lane when Day metadata lacks a tag."""
    explicit = str(series_title or "").strip()
    if explicit:
        return explicit

    text = f"{topic} {title}".lower()
    if any(k in text for k in ["로마", "중세", "기사", "군단", "바이킹", "스파르타", "전사", "hoplite", "viking", "sparta", "roman", "knight"]):
        return "최강역사대전"
    if any(k in text for k in ["공룡", "티라노", "트리케라", "dinosaur", "tyranno", "raptor"]):
        return "최강공룡대전"
    if any(k in text for k in ["우주", "행성", "블랙홀", "태양", "은하", "space", "planet", "black hole", "galaxy"]):
        return "최강우주대전"
    if any(k in text for k in ["몬스터", "괴물", "monster", "kaiju"]):
        return "최강몬스터대전"
    if any(k in text for k in ["심해", "바다", "상어", "범고래", "오징어", "ocean", "shark", "orca", "squid"]):
        return "최강심해대전"
    if any(k in text for k in ["동물", "호랑이", "사자", "곰", "악어", "animal", "tiger", "lion", "bear", "crocodile"]):
        return "최강동물대전"
    return "최강VS대전"


def _has_who_wins(format_type: str | None, cuts: Any) -> bool:
    if (format_type or "").upper() == "WHO_WINS":
        return True
    return any(str(cut.get("format_type") or "").upper() == "WHO_WINS" for cut in _iter_cuts(cuts))


def record_who_wins_episode(
    *,
    series_title: str | None = None,
    topic: str = "",
    title: str = "",
    cuts: Any = None,
    channel: str = "",
    video_url: str = "",
    publish_at: str | None = None,
    task_date: str | None = None,
    topic_group: str | None = None,
    source_file: str | None = None,
    format_type: str | None = None,
) -> dict[str, Any] | None:
    """Persist one successful WHO_WINS episode and its final-cut next teaser."""
    if not _has_who_wins(format_type, cuts):
        return None

    final_series_title = infer_series_title(topic, title, series_title)
    path = _series_path(final_series_title)
    payload = _load_series(path)
    if not payload:
        payload = {
            "series_id": _safe_slug(final_series_title),
            "series_title": final_series_title,
            "status": "active",
            "format": "WHO_WINS",
            "description": "Runtime-tracked WHO_WINS continuation series",
        }

    runtime = payload.setdefault("runtime", {})
    episodes = runtime.setdefault("episodes", [])
    if not isinstance(episodes, list):
        episodes = []
        runtime["episodes"] = episodes

    matchup = extract_matchup(title) or extract_matchup(topic)
    if not matchup:
        for cut in _iter_cuts(cuts)[:2]:
            matchup = extract_matchup(_cut_text(cut))
            if matchup:
                break
    next_matchup = extract_next_matchup_from_cuts(cuts)
    winner = extract_winner_from_cuts(cuts, matchup)

    normalized_url = str(video_url or "").strip()
    now = _now_iso()
    existing_idx = None
    for idx, episode in enumerate(episodes):
        if not isinstance(episode, dict):
            continue
        if normalized_url and str(episode.get("youtube_url") or "").strip() == normalized_url:
            existing_idx = idx
            break
        if (
            title
            and task_date
            and str(episode.get("title") or "").strip() == title
            and str(episode.get("task_date") or "").strip() == task_date
            and str(episode.get("channel") or "").strip() == channel
        ):
            existing_idx = idx
            break

    if existing_idx is None:
        episode_number = len([ep for ep in episodes if isinstance(ep, dict)]) + 1
    else:
        try:
            episode_number = int(episodes[existing_idx].get("episode") or existing_idx + 1)
        except Exception:
            episode_number = existing_idx + 1

    episode_payload = {
        "episode": episode_number,
        "task_date": task_date or "",
        "channel": channel or "",
        "topic": topic or "",
        "topic_group": topic_group or "",
        "title": title or "",
        "matchup": matchup or "",
        "winner": winner or "",
        "next_matchup": next_matchup or "",
        "youtube_url": normalized_url,
        "publish_at": publish_at or "",
        "source_file": source_file or "",
        "recorded_at": now,
    }
    if existing_idx is None:
        episodes.append(episode_payload)
    else:
        previous = episodes[existing_idx] if isinstance(episodes[existing_idx], dict) else {}
        episodes[existing_idx] = {**previous, **episode_payload}

    runtime.update({
        "updated_at": now,
        "next_episode": episode_number + 1,
        "last_matchup": matchup or runtime.get("last_matchup") or "",
        "last_winner": winner or runtime.get("last_winner") or "",
        "next_matchup": next_matchup or runtime.get("next_matchup") or "",
        "last_channel": channel or runtime.get("last_channel") or "",
        "last_title": title or runtime.get("last_title") or "",
    })
    payload["status"] = payload.get("status") or "active"
    payload["format"] = payload.get("format") or "WHO_WINS"
    _write_json_atomic(path, payload)
    return {
        "series_title": final_series_title,
        "path": str(path),
        "episode": episode_payload,
        "runtime": runtime,
    }


def _static_next_matchup(payload: dict[str, Any]) -> str:
    next_ep = payload.get("next_episode")
    bracket = payload.get("bracket") or {}
    if not isinstance(bracket, dict):
        return ""
    rounds = ["round_16", "quarter_final", "semi_final"]
    for round_name in rounds:
        items = bracket.get(round_name) or []
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if next_ep and item.get("ep") != next_ep:
                continue
            title = str(item.get("title_ko") or item.get("title") or "").strip()
            if title:
                return title
    return ""


def iter_series_payloads() -> list[tuple[Path, dict[str, Any]]]:
    if not SERIES_DIR.exists():
        return []
    payloads: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(SERIES_DIR.glob("*.json")):
        payload = _load_series(path)
        if payload:
            payloads.append((path, payload))
    return payloads


def build_active_series_context(max_items: int = 5) -> str:
    """Build a compact planner prompt block from runtime series state."""
    required: list[str] = []
    optional: list[str] = []

    for _path, payload in iter_series_payloads():
        if str(payload.get("status") or "active").lower() not in {"active", "running"}:
            continue
        series_title = str(payload.get("series_title") or payload.get("series_id") or "").strip()
        if not series_title:
            continue
        runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
        next_matchup = str(runtime.get("next_matchup") or "").strip()
        if next_matchup:
            previous = str(runtime.get("last_matchup") or "").strip()
            winner = str(runtime.get("last_winner") or "").strip()
            episode = runtime.get("next_episode") or "?"
            required.append(
                f"- [시리즈:{series_title}] 다음 에피소드 EP{episode}: {next_matchup}. "
                f"이전편: {previous or '미기록'}. 이전 승자: {winner or '미기록'}. "
                "반드시 다음 Day 후보에 [포맷:WHO_WINS]로 편성."
            )
            continue

        static_matchup = _static_next_matchup(payload)
        if static_matchup:
            optional.append(
                f"- [시리즈:{series_title}] 선택 후보: {static_matchup}. "
                "실제 업로드 후속 예고가 없을 때만 사용."
            )

    lines = ["## VS 시리즈 연속성 상태"]
    if required:
        lines.append("[필수 후속 VS]")
        lines.extend(required[:max_items])
    else:
        lines.append("[필수 후속 VS]")
        lines.append("- 현재 업로드가 예고한 필수 후속 VS 없음.")

    if optional:
        remaining = max(0, max_items - len(required))
        if remaining:
            lines.append("[선택 가능한 기존 토너먼트]")
            lines.extend(optional[:remaining])
    return "\n".join(lines)


def build_series_episode_context(
    series_title: str | None,
    current_topic: str = "",
    format_type: str | None = None,
) -> str | None:
    """Build a script-generation context for a single WHO_WINS episode."""
    if (format_type or "").upper() != "WHO_WINS" and not series_title:
        return None

    final_series_title = infer_series_title(current_topic, series_title=series_title)
    payload = _load_series(_series_path(final_series_title))
    runtime = payload.get("runtime") if isinstance(payload.get("runtime"), dict) else {}
    lines = [f"series_title: {final_series_title}"]
    current_matchup = extract_matchup(current_topic)
    if current_matchup:
        lines.append(f"current_matchup: {current_matchup}")
    if runtime:
        if runtime.get("last_matchup"):
            lines.append(f"previous_matchup: {runtime.get('last_matchup')}")
        if runtime.get("last_winner"):
            lines.append(f"previous_winner: {runtime.get('last_winner')}")
        if runtime.get("next_matchup"):
            lines.append(f"required_current_matchup_from_last_teaser: {runtime.get('next_matchup')}")
        if runtime.get("next_episode"):
            lines.append(f"episode_number: {runtime.get('next_episode')}")
    lines.append(
        "continuity_rule: this episode must continue the VS/tournament; "
        "use the current matchup as the episode and tease a new next matchup in the final cut."
    )
    return "\n".join(lines)
