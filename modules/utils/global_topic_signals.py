"""Global/country benchmark topic signals.

This stores external channel/topic signals separately from our upload history.
The generator may use these as inspiration, but must not copy titles verbatim.
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any


DB_PATH = os.path.join("data", "global_topic_signals.db")
CHANNEL_BENCHMARK_TARGETS: list[tuple[str, str, str]] = [
    ("askanything", "KR", "ko"),
    ("wonderdrop", "US", "en"),
    ("exploratodo", "MX", "es"),
    ("prismtale", "US_HISPANIC", "es"),
]


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _normalize(text: str) -> str:
    text = re.sub(r"\[[^\]]+\]", " ", text or "")
    text = text.lower()
    text = re.sub(r"[^0-9a-z가-힣áéíóúüñ¿?]+", "", text)
    return text.strip()


def _int_env(name: str, default: int, minimum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)).strip())
    except Exception:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    return value


def _benchmark_min_views() -> int:
    return _int_env("TOPIC_BENCHMARK_MIN_VIEWS", 1_000_000, minimum=1)


def _benchmark_fallback_min_views() -> int:
    primary = _benchmark_min_views()
    fallback = _int_env("TOPIC_BENCHMARK_FALLBACK_MIN_VIEWS", 600_000, minimum=1)
    return min(primary, fallback)


def _benchmark_min_signals_per_market() -> int:
    return _int_env("TOPIC_BENCHMARK_MIN_SIGNALS_PER_MARKET", 8, minimum=1)


def _benchmark_published_after() -> str | None:
    days = _int_env("TOPIC_BENCHMARK_PUBLISHED_AFTER_DAYS", 90, minimum=0)
    if days <= 0:
        return None
    value = datetime.now(timezone.utc) - timedelta(days=days)
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _benchmark_filters(min_views: int | None = None) -> tuple[list[str], list[Any]]:
    where = ["views >= ?"]
    params: list[Any] = [int(min_views or _benchmark_min_views())]
    published_after = _benchmark_published_after()
    if published_after:
        where.append("published_at IS NOT NULL")
        where.append("published_at >= ?")
        params.append(published_after)
    return where, params


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row["name"]) for row in rows}


def ensure_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS global_topic_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL DEFAULT 'benchmark_channel',
                source_channel TEXT NOT NULL,
                market TEXT NOT NULL DEFAULT 'GLOBAL',
                locale TEXT NOT NULL,
                title TEXT NOT NULL,
                normalized_title TEXT NOT NULL,
                canonical_topic TEXT NOT NULL,
                topic_key TEXT NOT NULL,
                hook TEXT,
                category TEXT,
                format_hint TEXT,
                views INTEGER DEFAULT 0,
                published_at TEXT,
                fetched_at TEXT NOT NULL,
                notes TEXT,
                UNIQUE(source_channel, normalized_title)
            )
            """
        )
        columns = _table_columns(conn, "global_topic_signals")
        if "market" not in columns:
            conn.execute("ALTER TABLE global_topic_signals ADD COLUMN market TEXT NOT NULL DEFAULT 'GLOBAL'")
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_global_topic_signals_score
            ON global_topic_signals(locale, published_at DESC, views DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_global_topic_signals_market_score
            ON global_topic_signals(market, locale, published_at DESC, views DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_global_topic_signals_topic_key
            ON global_topic_signals(topic_key)
            """
        )


def upsert_signal(
    *,
    source_channel: str,
    locale: str,
    title: str,
    canonical_topic: str,
    topic_key: str,
    market: str = "GLOBAL",
    source_type: str = "benchmark_channel",
    hook: str | None = None,
    category: str | None = None,
    format_hint: str | None = None,
    views: int = 0,
    published_at: str | None = None,
    notes: str | None = None,
) -> None:
    ensure_db()
    fetched_at = datetime.now().isoformat()
    normalized_title = _normalize(title)
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO global_topic_signals (
                source_type, source_channel, market, locale, title, normalized_title,
                canonical_topic, topic_key, hook, category, format_hint,
                views, published_at, fetched_at, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_channel, normalized_title) DO UPDATE SET
                source_type=excluded.source_type,
                market=excluded.market,
                locale=excluded.locale,
                title=excluded.title,
                canonical_topic=excluded.canonical_topic,
                topic_key=excluded.topic_key,
                hook=excluded.hook,
                category=excluded.category,
                format_hint=excluded.format_hint,
                views=excluded.views,
                published_at=excluded.published_at,
                fetched_at=excluded.fetched_at,
                notes=excluded.notes
            """,
            (
                source_type,
                source_channel,
                str(market or "GLOBAL").strip().upper(),
                locale,
                title,
                normalized_title,
                canonical_topic,
                topic_key,
                hook,
                category,
                format_hint,
                int(views or 0),
                published_at,
                fetched_at,
                notes,
            ),
        )


def list_signals(
    *,
    market: str | None = None,
    locale: str | None = None,
    category: str | None = None,
    format_hint: str | None = None,
    limit: int = 80,
    benchmark_filters: bool = True,
    min_views: int | None = None,
) -> list[dict[str, Any]]:
    ensure_db()
    where: list[str] = []
    params: list[Any] = []
    if benchmark_filters:
        filter_where, filter_params = _benchmark_filters(min_views=min_views)
        where.extend(filter_where)
        params.extend(filter_params)
    if market:
        where.append("market = ?")
        params.append(str(market).strip().upper())
    if locale:
        where.append("locale = ?")
        params.append(locale)
    if category:
        where.append("category = ?")
        params.append(category)
    if format_hint:
        where.append("format_hint = ?")
        params.append(format_hint)

    sql = "SELECT * FROM global_topic_signals"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY published_at DESC, views DESC, fetched_at DESC LIMIT ?"
    params.append(max(1, min(int(limit), 500)))
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def prune_signals(
    *,
    min_views: int | None = None,
    published_after: str | None = None,
) -> int:
    """Remove rows that no longer satisfy the current benchmark policy."""
    ensure_db()
    min_views = _benchmark_min_views() if min_views is None else max(1, int(min_views))
    if published_after is None:
        published_after = _benchmark_published_after()

    where = ["views < ?"]
    params: list[Any] = [min_views]
    if published_after:
        where.append("published_at IS NULL")
        where.append("published_at < ?")
        params.append(published_after)

    with _connect() as conn:
        cur = conn.execute(
            f"DELETE FROM global_topic_signals WHERE {' OR '.join(where)}",
            params,
        )
        return int(cur.rowcount or 0)


def delete_signals_by_ids(ids: list[int]) -> int:
    """Delete specific cached benchmark rows by primary key."""
    ids = [int(row_id) for row_id in ids if int(row_id or 0) > 0]
    if not ids:
        return 0
    ensure_db()
    placeholders = ",".join("?" for _ in ids)
    with _connect() as conn:
        cur = conn.execute(
            f"DELETE FROM global_topic_signals WHERE id IN ({placeholders})",
            ids,
        )
        return int(cur.rowcount or 0)


def get_signal_summary(*, benchmark_filters: bool = False) -> dict[str, Any]:
    """Return a compact health summary for external benchmark signals."""
    ensure_db()
    where = ""
    params: list[Any] = []
    if benchmark_filters:
        filter_where, params = _benchmark_filters()
        where = "WHERE " + " AND ".join(filter_where)
    with _connect() as conn:
        row = conn.execute(
            f"""
            SELECT
                COUNT(*) AS total,
                MAX(views) AS max_views,
                MAX(fetched_at) AS last_fetched_at,
                COUNT(DISTINCT source_channel) AS source_channels,
                COUNT(DISTINCT market) AS markets
            FROM global_topic_signals
            {where}
            """,
            params,
        ).fetchone()
    return dict(row) if row else {
        "total": 0,
        "max_views": 0,
        "last_fetched_at": None,
        "source_channels": 0,
        "markets": 0,
    }


def build_topic_signals_context(limit: int = 30) -> str:
    """Compact prompt context for topic generation."""
    per_target_limit = max(3, min(12, int(limit) // max(1, len(CHANNEL_BENCHMARK_TARGETS))))
    primary_min_views = _benchmark_min_views()
    fallback_min_views = _benchmark_fallback_min_views()
    min_market_signals = _benchmark_min_signals_per_market()
    target_rows: list[tuple[str, str, str, list[dict[str, Any]], str]] = []
    used_ids: set[int] = set()
    for channel, market, locale in CHANNEL_BENCHMARK_TARGETS:
        candidate_limit = max(per_target_limit, min_market_signals)
        rows = list_signals(
            market=market,
            locale=locale,
            limit=candidate_limit,
            min_views=primary_min_views,
        )
        tier_label = f"primary>={primary_min_views}"
        if len(rows) < min_market_signals and fallback_min_views < primary_min_views:
            fallback_rows = list_signals(
                market=market,
                locale=locale,
                limit=candidate_limit,
                min_views=fallback_min_views,
            )
            if len(fallback_rows) > len(rows):
                rows = fallback_rows
                tier_label = f"fallback>={fallback_min_views}"
        if not rows:
            rows = list_signals(
                locale=locale,
                limit=candidate_limit,
                min_views=fallback_min_views,
            )
            tier_label = f"locale fallback>={fallback_min_views}" if rows else tier_label
        rows = rows[:per_target_limit]
        for row in rows:
            row_id = int(row.get("id") or 0)
            if row_id:
                used_ids.add(row_id)
        target_rows.append((channel, market, locale, rows, tier_label))

    remaining_limit = max(0, int(limit) - len(used_ids))
    signals = [row for _, _, _, rows, _ in target_rows for row in rows]
    if remaining_limit:
        for row in list_signals(limit=remaining_limit):
            row_id = int(row.get("id") or 0)
            if row_id and row_id in used_ids:
                continue
            signals.append(row)
            if row_id:
                used_ids.add(row_id)
    if not signals:
        return (
            "외부 나라별/글로벌 벤치마크 신호 0건 — "
            "YOUTUBE_API_KEY_BENCHMARK 또는 TOPIC_BENCHMARK_SEARCH_QUERIES/"
            "TOPIC_BENCHMARK_CHANNEL_IDS 설정을 확인해야 한다. "
            "이 상태에서는 100만뷰 외부 모티브가 약해지고 내부 4채널 성과/최신성 후보만 보조로 쓰인다."
        )

    lines = [
        (
            "현재 외부 벤치마크 필터: "
            f"views>={_benchmark_min_views()}, "
            f"published_at>={_benchmark_published_after() or 'none'}"
        ),
        "외부 신호는 제목 복사용이 아니라 canonical topic/fingerprint 참고용이다.",
        "원문 제목을 그대로 쓰지 말고 우리 8포맷과 채널 톤으로 재작성한다.",
        (
            "채널별 주제선정은 언어가 아니라 market 기준을 우선한다: "
            "askanything=KR, wonderdrop=US, exploratodo=MX/LATAM, prismtale=US_HISPANIC."
        ),
        (
            f"벤치마크 tier: primary>={primary_min_views}, "
            f"market 후보가 {min_market_signals}개 미만이면 fallback>={fallback_min_views}까지 확장한다."
        ),
    ]
    for channel, market, locale, rows, tier_label in target_rows:
        lines.append(f"\n### {channel} benchmark market={market} locale={locale} tier={tier_label}")
        if not rows:
            lines.append("- exact market 신호 없음")
            continue
        for row in rows:
            lines.append(_format_signal_row(row))

    extra_rows = [
        row for row in signals
        if int(row.get("id") or 0) not in {
            int(target_row.get("id") or 0)
            for _, _, _, rows, _ in target_rows
            for target_row in rows
        }
    ]
    if extra_rows:
        lines.append("\n### additional global benchmark motifs")
        for row in extra_rows[: max(0, int(limit) - sum(len(rows) for _, _, _, rows, _ in target_rows))]:
            lines.append(_format_signal_row(row))
    return "\n".join(lines)


def _format_signal_row(row: dict[str, Any]) -> str:
    bits = [
        f"market:{row.get('market') or 'GLOBAL'}",
        f"locale:{row.get('locale') or '?'}",
        f"category:{row.get('category') or '?'}",
        f"format:{row.get('format_hint') or '?'}",
        f"hook:{row.get('hook') or '?'}",
        f"views:{row.get('views') or 0}",
    ]
    return (
        "- "
        + " ".join(f"[{bit}]" for bit in bits)
        + f" {row.get('canonical_topic') or row.get('title')} :: key={row.get('topic_key')}"
    )
