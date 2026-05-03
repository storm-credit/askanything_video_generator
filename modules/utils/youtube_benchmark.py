"""Collect 1M+ external YouTube Shorts benchmark signals for topic planning.

The topic planner consumes ``global_topic_signals`` as motif inspiration. This
collector keeps that table populated from external YouTube search/channel data
without copying titles verbatim into our Day files.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from modules.utils.global_topic_signals import (
    delete_signals_by_ids,
    get_signal_summary,
    list_signals,
    prune_signals,
    upsert_signal,
)


DEFAULT_SEARCH_QUERIES: list[dict[str, str]] = [
    {"market": "US", "locale": "en", "query": "science facts shorts"},
    {"market": "US", "locale": "en", "query": "space facts shorts"},
    {"market": "US", "locale": "en", "query": "ocean facts shorts"},
    {"market": "US", "locale": "en", "query": "dinosaur facts shorts"},
    {"market": "US", "locale": "en", "query": "animal facts shorts"},
    {"market": "MX", "locale": "es", "query": "datos curiosos ciencia shorts"},
    {"market": "MX", "locale": "es", "query": "curiosidades del espacio shorts"},
    {"market": "MX", "locale": "es", "query": "misterios de ciencia shorts"},
    {"market": "US_HISPANIC", "locale": "es", "query": "science facts en español shorts"},
    {"market": "US_HISPANIC", "locale": "es", "query": "misterios ciencia español shorts"},
    {"market": "US_HISPANIC", "locale": "es", "query": "datos curiosos en español shorts"},
    {"market": "US_HISPANIC", "locale": "es", "query": "curiosidades ciencia en español shorts"},
    {"market": "US_HISPANIC", "locale": "es", "query": "cosas que no sabías ciencia shorts"},
    {"market": "US_HISPANIC", "locale": "es", "query": "misterios en español shorts"},
    {"market": "KR", "locale": "ko", "query": "과학 상식 쇼츠"},
    {"market": "KR", "locale": "ko", "query": "우주 과학 쇼츠"},
]

CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("우주/행성", ["space", "planet", "star", "black hole", "nasa", "mars", "moon", "sun", "alien", "우주", "행성", "별", "화성", "달", "외계", "sol", "luna", "marte"]),
    ("심해/바다", ["ocean", "sea", "deep sea", "shark", "whale", "바다", "심해", "상어", "고래", "oceano", "mar"]),
    ("공룡/고생물", ["dinosaur", "fossil", "t rex", "jurassic", "공룡", "화석", "dinosaurio", "fosil"]),
    ("동물", ["animal", "ant", "bird", "snake", "spider", "octopus", "동물", "개미", "새", "문어", "animal"]),
    ("인체/심리", ["human body", "body", "brain", "heart", "blood", "stomach", "lungs", "몸", "뇌", "심장", "피", "위장", "폐", "cuerpo", "cerebro"]),
    ("지구/자연", ["earth", "volcano", "earthquake", "mountain", "desert", "지구", "화산", "지진", "사막", "tierra", "volcan"]),
    ("역사/문명", ["ancient", "history", "egypt", "roman", "king", "문명", "역사", "고대", "로마", "이집트", "historia"]),
    ("물리/화학", ["physics", "chemical", "metal", "temperature", "energy", "물리", "화학", "금속", "온도", "energia"]),
]


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)).strip())
    except Exception:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _get_api_key() -> str:
    for name in (
        "YOUTUBE_API_KEY_BENCHMARK",
        "YOUTUBE_API_KEY",
        "YOUTUBE_API_KEY_ASKANYTHING",
        "YOUTUBE_API_KEY_WONDERDROP",
        "YOUTUBE_API_KEY_EXPLORATODO",
        "YOUTUBE_API_KEY_PRISMTALE",
    ):
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _normalize_market(value: str | None, locale: str | None = None) -> str:
    text = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
    if text in {"USHISPANIC", "USSPANISH", "US_ES", "HISPANIC"}:
        return "US_HISPANIC"
    if re.fullmatch(r"[A-Z]{2}", text) or text in {"US_HISPANIC", "GLOBAL"}:
        return text
    return _market_for_locale(locale or text)


def _market_for_locale(locale: str | None) -> str:
    lang = (locale or "").strip().lower()
    if lang.startswith("ko"):
        return "KR"
    if lang.startswith("es"):
        return "MX"
    if lang.startswith("en"):
        return "US"
    return "GLOBAL"


def _locale_for_market(market: str | None) -> str:
    normalized = _normalize_market(market)
    if normalized == "KR":
        return "ko"
    if normalized in {"MX", "ES", "US_HISPANIC"}:
        return "es"
    return "en"


def _region_code_for_market(market: str | None) -> str | None:
    normalized = _normalize_market(market)
    if normalized == "US_HISPANIC":
        return "US"
    if re.fullmatch(r"[A-Z]{2}", normalized):
        return normalized
    return None


def _looks_like_locale(value: str | None) -> bool:
    return bool(re.fullmatch(r"[a-z]{2}(?:-[A-Z]{2})?", str(value or "").strip()))


def _looks_like_market(value: str | None) -> bool:
    text = str(value or "").strip().upper().replace("-", "_")
    return bool(re.fullmatch(r"[A-Z]{2}", text) or text in {"US_HISPANIC", "USHISPANIC", "US_ES"})


def _build_search_seed(market: str | None, locale: str | None, query: str) -> dict[str, str]:
    resolved_locale = (locale or "").strip() or _guess_locale(query)
    resolved_market = _normalize_market(market, resolved_locale)
    return {
        "market": resolved_market,
        "locale": resolved_locale,
        "query": query.strip(),
    }


def _parse_search_queries() -> list[dict[str, str]]:
    raw = os.getenv("TOPIC_BENCHMARK_SEARCH_QUERIES", "").strip()
    if not raw:
        return DEFAULT_SEARCH_QUERIES

    queries: list[dict[str, str]] = []
    for entry in re.split(r"[;\n]+", raw):
        entry = entry.strip()
        if not entry:
            continue
        if "|" in entry:
            parts = [part.strip() for part in entry.split("|")]
            if len(parts) >= 3:
                market, locale = parts[0], parts[1]
                query = "|".join(parts[2:]).strip()
                queries.append(_build_search_seed(market, locale, query))
            elif _looks_like_market(parts[0]) and not _looks_like_locale(parts[0]):
                market = parts[0]
                queries.append(_build_search_seed(market, _locale_for_market(market), parts[1]))
            else:
                locale = parts[0]
                queries.append(_build_search_seed(_market_for_locale(locale), locale, parts[1]))
        else:
            locale = _guess_locale(entry)
            queries.append(_build_search_seed(_market_for_locale(locale), locale, entry))
    return queries or DEFAULT_SEARCH_QUERIES


def _parse_channel_seeds() -> list[dict[str, str]]:
    raw = os.getenv("TOPIC_BENCHMARK_CHANNEL_IDS", "").strip()
    if not raw:
        return []

    seeds: list[dict[str, str]] = []
    for entry in re.split(r"[;\n]+", raw):
        parts = [p.strip() for p in entry.split("|") if p.strip()]
        if not parts:
            continue
        if len(parts) == 1:
            seeds.append({"market": "US", "locale": "en", "label": parts[0], "channel_id": parts[0]})
        elif len(parts) == 2:
            if _looks_like_market(parts[0]) and not _looks_like_locale(parts[0]):
                market = _normalize_market(parts[0])
                seeds.append({"market": market, "locale": _locale_for_market(market), "label": parts[1], "channel_id": parts[1]})
            else:
                locale = parts[0]
                seeds.append({"market": _market_for_locale(locale), "locale": locale, "label": parts[1], "channel_id": parts[1]})
        elif len(parts) == 3 and _looks_like_market(parts[0]) and _looks_like_locale(parts[1]):
            seeds.append({"market": _normalize_market(parts[0], parts[1]), "locale": parts[1], "label": parts[2], "channel_id": parts[2]})
        else:
            if len(parts) >= 4:
                seeds.append({"market": _normalize_market(parts[0], parts[1]), "locale": parts[1], "label": parts[2], "channel_id": parts[3]})
            else:
                locale = parts[0]
                seeds.append({"market": _market_for_locale(locale), "locale": locale, "label": parts[1], "channel_id": parts[2]})
    return seeds


def _guess_locale(text: str) -> str:
    lowered = (text or "").lower()
    if re.search(r"[가-힣]", text or ""):
        return "ko"
    if re.search(
        r"[¿¡áéíóúüñ]"
        r"|\b(el|la|los|las|un|una|unos|unas|del|de|por|porque|qué|que|si|"
        r"datos|ciencia|curiosidades|espacio|tierra|luna|marte|planeta|"
        r"animales|dinosaurios|misterio|secreto|volc[aá]n)\b",
        lowered,
        re.IGNORECASE,
    ):
        return "es"
    return "en"


def _looks_portuguese(text: str) -> bool:
    lowered = (text or "").lower()
    return bool(
        re.search(
            r"[ãõç]"
            r"|\b(voc[eê]|quanto tempo|levaria|chegar|superf[ií]cie|"
            r"antes da|antes do|uma|você|eles|sem se|molhar|bola|oceano)\b",
            lowered,
            re.IGNORECASE,
        )
    )


def _is_locale_compatible(title: str, locale: str | None) -> bool:
    target = _lang_for_hook(locale or "")
    detected = _guess_locale(title)
    if target == "ko":
        return detected == "ko"
    if target == "es":
        return detected == "es" and not _looks_portuguese(title)
    if target == "en":
        return detected == "en"
    return True


def _prune_incompatible_cached_signals() -> int:
    stale_ids: list[int] = []
    for row in list_signals(limit=500, benchmark_filters=False):
        market = str(row.get("market") or "GLOBAL").strip().upper()
        if market == "GLOBAL":
            continue
        if not _is_locale_compatible(str(row.get("title") or ""), str(row.get("locale") or "")):
            stale_ids.append(int(row.get("id") or 0))
    return delete_signals_by_ids(stale_ids)


def _lang_for_hook(locale: str) -> str:
    locale = (locale or "en").lower()
    if locale.startswith("ko"):
        return "ko"
    if locale.startswith("es"):
        return "es"
    return "en"


def _youtube_get(endpoint: str, params: dict[str, Any], api_key: str) -> dict[str, Any]:
    params = {**params, "key": api_key}
    resp = requests.get(
        f"https://www.googleapis.com/youtube/v3/{endpoint}",
        params=params,
        timeout=20,
    )
    try:
        data = resp.json()
    except Exception:
        data = {}
    if resp.status_code >= 400:
        message = data.get("error", {}).get("message") or resp.text[:240]
        raise RuntimeError(f"YouTube API {endpoint} failed: {message}")
    return data


def _published_after() -> str | None:
    days = _int_env("TOPIC_BENCHMARK_PUBLISHED_AFTER_DAYS", 90, minimum=0)
    if days <= 0:
        return None
    value = datetime.now(timezone.utc) - timedelta(days=days)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _search_video_ids(
    *,
    api_key: str,
    query: str | None = None,
    channel_id: str | None = None,
    max_results: int,
    locale: str,
    market: str | None = None,
) -> list[str]:
    params: dict[str, Any] = {
        "part": "snippet",
        "type": "video",
        "order": os.getenv("TOPIC_BENCHMARK_SEARCH_ORDER", "viewCount").strip() or "viewCount",
        "videoDuration": "short",
        "maxResults": min(max_results, 50),
        "safeSearch": "none",
    }
    if query:
        params["q"] = query
    if channel_id:
        params["channelId"] = channel_id
    if locale:
        params["relevanceLanguage"] = _lang_for_hook(locale)
    region_code = _region_code_for_market(market)
    if region_code:
        params["regionCode"] = region_code
    published_after = _published_after()
    if published_after:
        params["publishedAfter"] = published_after

    data = _youtube_get("search", params, api_key)
    ids: list[str] = []
    for item in data.get("items", []):
        video_id = item.get("id", {}).get("videoId")
        if video_id:
            ids.append(video_id)
    return ids


def _fetch_video_details(api_key: str, video_ids: list[str]) -> list[dict[str, Any]]:
    if not video_ids:
        return []
    details: list[dict[str, Any]] = []
    for start in range(0, len(video_ids), 50):
        batch = video_ids[start : start + 50]
        data = _youtube_get(
            "videos",
            {
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(batch),
                "maxResults": len(batch),
            },
            api_key,
        )
        details.extend(data.get("items", []))
    return details


def _own_channel_ids() -> set[str]:
    try:
        from modules.utils.youtube_stats import _load_channel_ids

        return {v for v in _load_channel_ids().values() if v}
    except Exception:
        return set()


def _clean_title(title: str) -> str:
    title = re.sub(r"#\w+", " ", title or "")
    title = re.sub(r"\s+", " ", title).strip(" -|")
    return title[:160]


def _normalize_key(text: str) -> str:
    text = re.sub(r"#\w+", " ", text or "")
    text = text.lower()
    text = re.sub(r"[^0-9a-z가-힣áéíóúüñ¿?]+", "", text)
    return text.strip()


def _topic_key(title: str, category: str) -> str:
    compact = _normalize_key(title)
    digest = hashlib.sha1(compact.encode("utf-8")).hexdigest()[:12]
    return f"{category}:{digest}"


def _classify_category(title: str) -> str:
    lower = (title or "").lower()
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword.lower() in lower for keyword in keywords):
            return category
    return "기타"


def _classify_hooks(title: str, locale: str) -> list[str]:
    try:
        from modules.analytics.performance_tracker import _classify_hook

        return _classify_hook(title, _lang_for_hook(locale))
    except Exception:
        return []


def _infer_format_hint(hooks: list[str], title: str) -> str:
    title_lower = title.lower()
    if "comparison" in hooks or re.search(r"\bvs\.?\b| 대 ", title_lower):
        return "WHO_WINS"
    if "question" in hooks or title.strip().endswith("?"):
        return "IF"
    if "negation_reveal" in hooks:
        return "PARADOX"
    if "hidden_secret" in hooks:
        return "MYSTERY"
    if "number_shock" in hooks:
        return "SCALE"
    if "sensory" in hooks:
        return "EMOTIONAL_SCI"
    return "FACT"


def _is_recent_enough(last_fetched_at: str | None, ttl_hours: int) -> bool:
    if not last_fetched_at or ttl_hours <= 0:
        return False
    try:
        value = datetime.fromisoformat(last_fetched_at)
    except Exception:
        return False
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - value.astimezone(timezone.utc) < timedelta(hours=ttl_hours)


def refresh_global_topic_signals(*, force: bool = False) -> dict[str, Any]:
    """Fetch external 1M+ YouTube Shorts signals into global_topic_signals."""
    if not _truthy(os.getenv("TOPIC_BENCHMARK_ENABLED"), default=True):
        return {"success": False, "skipped": True, "reason": "TOPIC_BENCHMARK_ENABLED=false"}

    primary_min_views = _int_env("TOPIC_BENCHMARK_MIN_VIEWS", 1_000_000, minimum=1)
    fallback_min_views = min(
        primary_min_views,
        _int_env("TOPIC_BENCHMARK_FALLBACK_MIN_VIEWS", 600_000, minimum=1),
    )
    min_views = fallback_min_views
    published_after = _published_after()
    pruned = prune_signals(min_views=min_views, published_after=published_after)
    incompatible_pruned = _prune_incompatible_cached_signals()
    summary = get_signal_summary(benchmark_filters=True)
    ttl_hours = _int_env("TOPIC_BENCHMARK_REFRESH_TTL_HOURS", 24, minimum=0)
    if (
        not force
        and int(summary.get("total") or 0) > 0
        and _is_recent_enough(summary.get("last_fetched_at"), ttl_hours)
    ):
        return {
            "success": True,
            "skipped": True,
            "reason": "fresh_cache",
            "pruned": pruned,
            "incompatible_pruned": incompatible_pruned,
            "primary_min_views": primary_min_views,
            "fallback_min_views": fallback_min_views,
            "collection_min_views": min_views,
            "published_after": published_after,
            "summary": summary,
        }

    api_key = _get_api_key()
    if not api_key:
        return {
            "success": False,
            "skipped": True,
            "reason": "YOUTUBE_API_KEY_BENCHMARK/YOUTUBE_API_KEY 없음",
            "pruned": pruned,
            "incompatible_pruned": incompatible_pruned,
            "primary_min_views": primary_min_views,
            "fallback_min_views": fallback_min_views,
            "collection_min_views": min_views,
            "published_after": published_after,
            "summary": summary,
        }

    max_results = _int_env("TOPIC_BENCHMARK_MAX_RESULTS_PER_QUERY", 25, minimum=1, maximum=50)
    own_channels = _own_channel_ids()

    scanned = 0
    stored = 0
    below_threshold = 0
    own_skipped = 0
    off_topic_skipped = 0
    locale_mismatch_skipped = 0
    errors: list[str] = []
    seen_video_ids: set[str] = set()

    seeds: list[dict[str, str]] = [
        {"type": "query", **seed}
        for seed in _parse_search_queries()
    ]
    seeds.extend({"type": "channel", **seed} for seed in _parse_channel_seeds())

    for seed in seeds:
        try:
            if seed["type"] == "channel":
                ids = _search_video_ids(
                    api_key=api_key,
                    channel_id=seed["channel_id"],
                    max_results=max_results,
                    locale=seed.get("locale", "en"),
                    market=seed.get("market"),
                )
                seed_note = f"market:{seed.get('market', 'GLOBAL')} channel:{seed.get('label') or seed['channel_id']}"
            else:
                ids = _search_video_ids(
                    api_key=api_key,
                    query=seed["query"],
                    max_results=max_results,
                    locale=seed.get("locale", "en"),
                    market=seed.get("market"),
                )
                seed_note = f"market:{seed.get('market', 'GLOBAL')} query:{seed['query']}"
        except Exception as e:
            errors.append(f"{seed.get('query') or seed.get('channel_id')}: {e}")
            continue

        ids = [video_id for video_id in ids if video_id not in seen_video_ids]
        seen_video_ids.update(ids)
        try:
            videos = _fetch_video_details(api_key, ids)
        except Exception as e:
            errors.append(f"{seed_note}: {e}")
            continue

        for item in videos:
            scanned += 1
            snippet = item.get("snippet", {})
            statistics = item.get("statistics", {})
            channel_id = snippet.get("channelId", "")
            if channel_id in own_channels:
                own_skipped += 1
                continue

            try:
                views = int(statistics.get("viewCount", 0))
            except Exception:
                views = 0
            if views < min_views:
                below_threshold += 1
                continue

            published_at = snippet.get("publishedAt")
            if published_after and (not published_at or published_at < published_after):
                continue

            raw_title = snippet.get("title", "")
            title = _clean_title(raw_title)
            if not title:
                continue
            locale = seed.get("locale") or _guess_locale(title)
            if not _is_locale_compatible(title, locale):
                locale_mismatch_skipped += 1
                continue
            market = _normalize_market(seed.get("market"), locale)
            hooks = _classify_hooks(title, locale)
            category = _classify_category(title)
            if category == "기타" and not _truthy(os.getenv("TOPIC_BENCHMARK_ALLOW_MISC"), default=False):
                off_topic_skipped += 1
                continue
            format_hint = _infer_format_hint(hooks, title)
            video_id = item.get("id", "")
            url = f"https://www.youtube.com/shorts/{video_id}" if video_id else ""
            source_channel = snippet.get("channelTitle") or channel_id or "unknown"

            upsert_signal(
                source_type="youtube_search_1m" if seed["type"] == "query" else "benchmark_channel",
                source_channel=source_channel,
                market=market,
                locale=locale,
                title=title,
                canonical_topic=title,
                topic_key=_topic_key(title, category),
                hook=",".join(hooks) if hooks else None,
                category=category,
                format_hint=format_hint,
                views=views,
                published_at=published_at,
                notes=json.dumps(
                    {
                        "video_id": video_id,
                        "url": url,
                        "seed": seed_note,
                        "channel_id": channel_id,
                        "market": market,
                        "region_code": _region_code_for_market(market),
                    },
                    ensure_ascii=False,
                ),
            )
            stored += 1

    return {
        "success": stored > 0,
        "scanned": scanned,
        "stored": stored,
        "below_threshold": below_threshold,
        "own_skipped": own_skipped,
        "off_topic_skipped": off_topic_skipped,
        "locale_mismatch_skipped": locale_mismatch_skipped,
        "primary_min_views": primary_min_views,
        "fallback_min_views": fallback_min_views,
        "collection_min_views": min_views,
        "published_after": published_after,
        "pruned": pruned,
        "incompatible_pruned": incompatible_pruned,
        "errors": errors[:10],
        "summary": get_signal_summary(benchmark_filters=True),
    }
