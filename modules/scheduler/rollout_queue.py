"""Lead-channel-first holdback expansion queue.

Stores prior-day holdback channels and promotes them after the lead video
passes a simple 24-hour performance gate.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any


DB_PATH = os.path.join("data", "rollout_queue.db")
KST = timezone(timedelta(hours=9))
FINAL_STATUSES = {"expanded", "skipped"}


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rollout_expansions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_task_date TEXT NOT NULL,
                topic_group TEXT NOT NULL,
                lead_channel TEXT NOT NULL,
                holdback_payload TEXT NOT NULL,
                format_type TEXT,
                series_title TEXT,
                source_file TEXT,
                lead_publish_at TEXT NOT NULL,
                expand_after TEXT NOT NULL,
                lead_video_url TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                metric_views INTEGER,
                threshold_views INTEGER,
                last_error TEXT,
                evaluated_at TEXT,
                expanded_task_date TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (lead_task_date, topic_group, lead_channel)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_rollout_expansions_due
            ON rollout_expansions(status, expand_after)
            """
        )


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_load(value: str | None) -> Any:
    if not value:
        return {}
    try:
        return json.loads(value)
    except Exception:
        return {}


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    data["holdback_payload"] = _json_load(data.get("holdback_payload"))
    return data


def register_candidate(
    *,
    lead_task_date: str,
    topic_group: str,
    lead_channel: str,
    holdback_payload: dict[str, Any],
    format_type: str | None,
    series_title: str | None,
    source_file: str | None,
    lead_publish_at: str,
    lead_video_url: str | None,
) -> dict[str, Any]:
    ensure_db()
    now = datetime.now(KST).isoformat()
    expand_after = (
        datetime.fromisoformat(lead_publish_at.replace("Z", "+00:00"))
        .astimezone(KST)
        + timedelta(hours=max(1, int(os.getenv("ROLLOUT_EXPANSION_DELAY_HOURS", "24"))))
    ).isoformat()

    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO rollout_expansions (
                lead_task_date, topic_group, lead_channel, holdback_payload,
                format_type, series_title, source_file, lead_publish_at,
                expand_after, lead_video_url, status, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            ON CONFLICT(lead_task_date, topic_group, lead_channel) DO UPDATE SET
                holdback_payload=excluded.holdback_payload,
                format_type=COALESCE(excluded.format_type, rollout_expansions.format_type),
                series_title=COALESCE(excluded.series_title, rollout_expansions.series_title),
                source_file=COALESCE(excluded.source_file, rollout_expansions.source_file),
                lead_publish_at=excluded.lead_publish_at,
                expand_after=excluded.expand_after,
                lead_video_url=COALESCE(excluded.lead_video_url, rollout_expansions.lead_video_url),
                status=CASE
                    WHEN rollout_expansions.status IN ('expanded', 'skipped')
                        THEN rollout_expansions.status
                    ELSE 'pending'
                END,
                last_error=NULL,
                updated_at=excluded.updated_at
            """,
            (
                lead_task_date,
                topic_group,
                lead_channel,
                _json_dump(holdback_payload),
                format_type,
                series_title,
                source_file,
                lead_publish_at,
                expand_after,
                lead_video_url,
                now,
                now,
            ),
        )
        row = conn.execute(
            """
            SELECT *
            FROM rollout_expansions
            WHERE lead_task_date = ?
              AND topic_group = ?
              AND lead_channel = ?
            """,
            (lead_task_date, topic_group, lead_channel),
        ).fetchone()
    return _row_to_dict(row) or {}


def claim_due_candidates(limit: int = 10, now: datetime | None = None) -> list[dict[str, Any]]:
    ensure_db()
    now_dt = (now or datetime.now(KST)).astimezone(KST)
    now_iso = now_dt.isoformat()
    stale_before = (now_dt - timedelta(hours=6)).isoformat()

    with _connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            UPDATE rollout_expansions
            SET status = 'pending',
                updated_at = ?
            WHERE status = 'processing'
              AND updated_at < ?
            """,
            (now_iso, stale_before),
        )
        rows = conn.execute(
            """
            SELECT *
            FROM rollout_expansions
            WHERE status = 'pending'
              AND expand_after <= ?
            ORDER BY expand_after ASC, id ASC
            LIMIT ?
            """,
            (now_iso, max(1, int(limit))),
        ).fetchall()
        ids = [int(row["id"]) for row in rows]
        if ids:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                f"""
                UPDATE rollout_expansions
                SET status = 'processing',
                    updated_at = ?
                WHERE id IN ({placeholders})
                  AND status = 'pending'
                """,
                [now_iso, *ids],
            )
            rows = conn.execute(
                f"""
                SELECT *
                FROM rollout_expansions
                WHERE id IN ({placeholders})
                ORDER BY expand_after ASC, id ASC
                """,
                ids,
            ).fetchall()
    return [_row_to_dict(row) or {} for row in rows]


def release_candidate(candidate_id: int, *, last_error: str | None = None) -> None:
    ensure_db()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE rollout_expansions
            SET status = 'pending',
                last_error = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (last_error, datetime.now(KST).isoformat(), int(candidate_id)),
        )


def mark_candidate_skipped(
    candidate_id: int,
    *,
    metric_views: int | None,
    threshold_views: int | None,
    last_error: str | None = None,
) -> None:
    ensure_db()
    now = datetime.now(KST).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE rollout_expansions
            SET status = 'skipped',
                metric_views = ?,
                threshold_views = ?,
                last_error = ?,
                evaluated_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (metric_views, threshold_views, last_error, now, now, int(candidate_id)),
        )


def mark_candidate_expanded(
    candidate_id: int,
    *,
    metric_views: int | None,
    threshold_views: int | None,
    expanded_task_date: str | None,
) -> None:
    ensure_db()
    now = datetime.now(KST).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE rollout_expansions
            SET status = 'expanded',
                metric_views = ?,
                threshold_views = ?,
                expanded_task_date = ?,
                evaluated_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (metric_views, threshold_views, expanded_task_date, now, now, int(candidate_id)),
        )


def mark_candidate_failed(candidate_id: int, *, last_error: str | None) -> None:
    ensure_db()
    now = datetime.now(KST).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            UPDATE rollout_expansions
            SET status = 'failed',
                last_error = ?,
                evaluated_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (last_error, now, now, int(candidate_id)),
        )


def list_candidates(*, status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    ensure_db()
    sql = "SELECT * FROM rollout_expansions"
    params: list[Any] = []
    if status:
        sql += " WHERE status = ?"
        params.append(status)
    sql += " ORDER BY expand_after DESC, id DESC LIMIT ?"
    params.append(max(1, min(int(limit), 500)))
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_dict(row) or {} for row in rows]


def get_queue_summary(now: datetime | None = None) -> dict[str, Any]:
    ensure_db()
    now_iso = (now or datetime.now(KST)).astimezone(KST).isoformat()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS cnt
            FROM rollout_expansions
            GROUP BY status
            """
        ).fetchall()
        due_row = conn.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM rollout_expansions
            WHERE status = 'pending'
              AND expand_after <= ?
            """,
            (now_iso,),
        ).fetchone()
    counts = {str(row["status"]): int(row["cnt"]) for row in rows}
    return {
        "counts": counts,
        "due_now": int(due_row["cnt"]) if due_row else 0,
        "pending": counts.get("pending", 0),
        "processing": counts.get("processing", 0),
    }
