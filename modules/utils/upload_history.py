"""YouTube 업로드 히스토리 DB.

목적:
  - 채널 실제 업로드 제목을 누적 저장
  - 최근 100개 캐시를 넘는 중복 축도 Day 생성 전에 차단
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime
from typing import Any


DB_PATH = os.path.join("data", "upload_history.db")


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS youtube_uploads (
                channel TEXT NOT NULL,
                video_id TEXT NOT NULL,
                title TEXT NOT NULL,
                normalized_title TEXT NOT NULL,
                published_at TEXT,
                fetched_at TEXT,
                source TEXT NOT NULL DEFAULT 'youtube_api',
                PRIMARY KEY (channel, video_id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_youtube_uploads_channel_published
            ON youtube_uploads(channel, published_at DESC)
            """
        )


def _normalize_title(text: str) -> str:
    text = re.sub(r"\[[^\]]+\]", " ", text or "")
    text = text.lower()
    text = re.sub(r"[^0-9a-z가-힣áéíóúüñ¿?]+", "", text)
    return text.strip()


def upsert_videos(channel: str, videos: list[dict[str, Any]], source: str = "youtube_api") -> int:
    ensure_db()
    fetched_at = datetime.now().isoformat()
    rows = [
        (
            channel,
            str(v.get("video_id", "")).strip(),
            str(v.get("title", "")).strip(),
            _normalize_title(str(v.get("title", "")).strip()),
            str(v.get("published_at", "")).strip(),
            fetched_at,
            source,
        )
        for v in videos
        if str(v.get("video_id", "")).strip() and str(v.get("title", "")).strip()
    ]
    if not rows:
        return 0

    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO youtube_uploads
                (channel, video_id, title, normalized_title, published_at, fetched_at, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(channel, video_id) DO UPDATE SET
                title=excluded.title,
                normalized_title=excluded.normalized_title,
                published_at=excluded.published_at,
                fetched_at=excluded.fetched_at,
                source=excluded.source
            """,
            rows,
        )

    try:
        from modules.utils.topic_memory import upsert_titles

        upsert_titles(channel, [row[2] for row in rows], source=source)
    except Exception as e:
        print(f"[Topic Memory] canonical sync skipped ({channel}): {e}")
    return len(rows)


def get_uploaded_titles(channel: str | None = None, limit: int | None = None) -> list[str]:
    ensure_db()
    sql = "SELECT title FROM youtube_uploads"
    params: list[Any] = []
    if channel:
        sql += " WHERE channel = ?"
        params.append(channel)
    sql += " ORDER BY published_at DESC, fetched_at DESC"
    if limit:
        sql += " LIMIT ?"
        params.append(limit)

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [str(r["title"]).strip() for r in rows if str(r["title"]).strip()]


def count_uploaded_records(channel: str | None = None) -> int:
    ensure_db()
    sql = "SELECT COUNT(*) AS cnt FROM youtube_uploads"
    params: list[Any] = []
    if channel:
        sql += " WHERE channel = ?"
        params.append(channel)
    with _connect() as conn:
        row = conn.execute(sql, params).fetchone()
    return int(row["cnt"]) if row else 0


def get_last_synced_at(channel: str | None = None) -> str | None:
    ensure_db()
    sql = "SELECT MAX(fetched_at) AS last_synced_at FROM youtube_uploads"
    params: list[Any] = []
    if channel:
        sql += " WHERE channel = ?"
        params.append(channel)
    with _connect() as conn:
        row = conn.execute(sql, params).fetchone()
    return str(row["last_synced_at"]) if row and row["last_synced_at"] else None


def sync_channel_history(channel: str, max_results: int = 500) -> int:
    """YouTube API로 채널 업로드 히스토리를 동기화한다."""
    from modules.utils.youtube_stats import fetch_channel_videos

    videos = fetch_channel_videos(channel, max_results=max_results)
    if not videos:
        return 0
    return upsert_videos(channel, videos, source="youtube_api")
