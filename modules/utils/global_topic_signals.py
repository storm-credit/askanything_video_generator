"""Global/country benchmark topic signals.

This stores external channel/topic signals separately from our upload history.
The generator may use these as inspiration, but must not copy titles verbatim.
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime
from typing import Any


DB_PATH = os.path.join("data", "global_topic_signals.db")


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


def ensure_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS global_topic_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_type TEXT NOT NULL DEFAULT 'benchmark_channel',
                source_channel TEXT NOT NULL,
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
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_global_topic_signals_score
            ON global_topic_signals(locale, published_at DESC, views DESC)
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
                source_type, source_channel, locale, title, normalized_title,
                canonical_topic, topic_key, hook, category, format_hint,
                views, published_at, fetched_at, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_channel, normalized_title) DO UPDATE SET
                source_type=excluded.source_type,
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
    locale: str | None = None,
    category: str | None = None,
    format_hint: str | None = None,
    limit: int = 80,
) -> list[dict[str, Any]]:
    ensure_db()
    where: list[str] = []
    params: list[Any] = []
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


def get_signal_summary() -> dict[str, Any]:
    """Return a compact health summary for external benchmark signals."""
    ensure_db()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                MAX(views) AS max_views,
                MAX(fetched_at) AS last_fetched_at,
                COUNT(DISTINCT source_channel) AS source_channels
            FROM global_topic_signals
            """
        ).fetchone()
    return dict(row) if row else {
        "total": 0,
        "max_views": 0,
        "last_fetched_at": None,
        "source_channels": 0,
    }


def build_topic_signals_context(limit: int = 30) -> str:
    """Compact prompt context for topic generation."""
    signals = list_signals(limit=limit)
    if not signals:
        return (
            "외부 나라별/글로벌 벤치마크 신호 0건 — "
            "YOUTUBE_API_KEY_BENCHMARK 또는 TOPIC_BENCHMARK_SEARCH_QUERIES/"
            "TOPIC_BENCHMARK_CHANNEL_IDS 설정을 확인해야 한다. "
            "이 상태에서는 100만뷰 외부 모티브가 약해지고 내부 4채널 성과/최신성 후보만 보조로 쓰인다."
        )

    lines = [
        "외부 신호는 제목 복사용이 아니라 canonical topic/fingerprint 참고용이다.",
        "원문 제목을 그대로 쓰지 말고 우리 8포맷과 채널 톤으로 재작성한다.",
    ]
    for row in signals:
        bits = [
            f"locale:{row.get('locale') or '?'}",
            f"category:{row.get('category') or '?'}",
            f"format:{row.get('format_hint') or '?'}",
            f"hook:{row.get('hook') or '?'}",
            f"views:{row.get('views') or 0}",
        ]
        lines.append(
            "- "
            + " ".join(f"[{bit}]" for bit in bits)
            + f" {row.get('canonical_topic') or row.get('title')} :: key={row.get('topic_key')}"
        )
    return "\n".join(lines)
