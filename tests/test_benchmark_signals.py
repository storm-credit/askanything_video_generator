from datetime import datetime, timezone

from modules.utils import global_topic_signals, youtube_benchmark


def test_parse_benchmark_queries_supports_market_locale_format(monkeypatch):
    monkeypatch.setenv(
        "TOPIC_BENCHMARK_SEARCH_QUERIES",
        "US|en|science facts shorts;MX|es|curiosidades ciencia shorts;ko|우주 과학 쇼츠",
    )

    seeds = youtube_benchmark._parse_search_queries()

    assert seeds[0] == {"market": "US", "locale": "en", "query": "science facts shorts"}
    assert seeds[1] == {"market": "MX", "locale": "es", "query": "curiosidades ciencia shorts"}
    assert seeds[2] == {"market": "KR", "locale": "ko", "query": "우주 과학 쇼츠"}


def test_search_uses_region_code_for_country_market(monkeypatch):
    captured = {}

    def fake_youtube_get(endpoint, params, api_key):
        captured["endpoint"] = endpoint
        captured["params"] = params
        captured["api_key"] = api_key
        return {"items": [{"id": {"videoId": "abc123"}}]}

    monkeypatch.setattr(youtube_benchmark, "_youtube_get", fake_youtube_get)

    ids = youtube_benchmark._search_video_ids(
        api_key="test-key",
        query="misterios ciencia español shorts",
        max_results=5,
        locale="es",
        market="US_HISPANIC",
    )

    assert ids == ["abc123"]
    assert captured["endpoint"] == "search"
    assert captured["params"]["regionCode"] == "US"
    assert captured["params"]["relevanceLanguage"] == "es"


def test_topic_signal_context_groups_by_channel_market(tmp_path, monkeypatch):
    monkeypatch.setattr(global_topic_signals, "DB_PATH", str(tmp_path / "signals.db"))
    monkeypatch.setenv("TOPIC_BENCHMARK_PUBLISHED_AFTER_DAYS", "365")
    published_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    rows = [
        ("KR", "ko", "한국 우주 샤워 100만뷰"),
        ("US", "en", "A Shower Could Break the ISS"),
        ("MX", "es", "Una ducha podría dañar la ISS"),
        ("US_HISPANIC", "es", "El agua prohibida de los astronautas"),
    ]
    for market, locale, title in rows:
        global_topic_signals.upsert_signal(
            source_channel=f"{market} source",
            market=market,
            locale=locale,
            title=title,
            canonical_topic=title,
            topic_key=f"우주/행성:{market}",
            category="우주/행성",
            format_hint="FACT",
            views=1_500_000,
            published_at=published_at,
        )

    context = global_topic_signals.build_topic_signals_context(limit=12)

    assert "askanything benchmark market=KR locale=ko" in context
    assert "wonderdrop benchmark market=US locale=en" in context
    assert "exploratodo benchmark market=MX locale=es" in context
    assert "prismtale benchmark market=US_HISPANIC locale=es" in context
    assert "orchestra expert directives" in context
    assert "[wonderdrop] expert=US Shorts strategist" in context
    assert "topic selection gate" in context
    assert "[market:US]" in context
    assert "[market:MX]" in context


def test_topic_signal_context_uses_600k_fallback_when_market_primary_is_sparse(tmp_path, monkeypatch):
    monkeypatch.setattr(global_topic_signals, "DB_PATH", str(tmp_path / "signals.db"))
    monkeypatch.setenv("TOPIC_BENCHMARK_PUBLISHED_AFTER_DAYS", "365")
    monkeypatch.setenv("TOPIC_BENCHMARK_MIN_VIEWS", "1000000")
    monkeypatch.setenv("TOPIC_BENCHMARK_FALLBACK_MIN_VIEWS", "600000")
    monkeypatch.setenv("TOPIC_BENCHMARK_MIN_SIGNALS_PER_MARKET", "8")
    published_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    global_topic_signals.upsert_signal(
        source_channel="US fallback source",
        market="US",
        locale="en",
        title="A 700K US Science Motif",
        canonical_topic="A 700K US Science Motif",
        topic_key="우주/행성:US700K",
        category="우주/행성",
        format_hint="FACT",
        views=700_000,
        published_at=published_at,
    )

    context = global_topic_signals.build_topic_signals_context(limit=12)

    assert "wonderdrop benchmark market=US locale=en tier=fallback>=600000" in context
    assert "A 700K US Science Motif" in context
