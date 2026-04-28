"""오늘 할 일 실행/완료 이력 DB.

Day 파일의 주제 상태를 산출물 유무와 별도로 보관한다.
크론 성공, 수동 완료, 과거 완료 처리 모두 이 DB를 기준으로 조회한다.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from typing import Any


DB_PATH = os.path.join("data", "today_tasks.db")
COMPLETED_STATUSES = {"completed", "success", "manual_completed"}


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_db() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS today_tasks (
                task_date TEXT NOT NULL,
                topic_group TEXT NOT NULL,
                channel TEXT NOT NULL,
                title TEXT,
                source_topic TEXT,
                status TEXT NOT NULL,
                source TEXT NOT NULL,
                note TEXT,
                source_file TEXT,
                video_path TEXT,
                youtube_url TEXT,
                publish_at TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (task_date, topic_group, channel)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_today_tasks_date_status
            ON today_tasks(task_date DESC, status)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_today_tasks_search
            ON today_tasks(topic_group, title)
            """
        )
        columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(today_tasks)").fetchall()
        }
        if "publish_at" not in columns:
            conn.execute("ALTER TABLE today_tasks ADD COLUMN publish_at TEXT")
        if "source_topic" not in columns:
            conn.execute("ALTER TABLE today_tasks ADD COLUMN source_topic TEXT")


def upsert_task_status(
    *,
    task_date: str,
    topic_group: str,
    channel: str,
    status: str,
    title: str | None = None,
    source_topic: str | None = None,
    source: str = "manual",
    note: str | None = None,
    source_file: str | None = None,
    video_path: str | None = None,
    youtube_url: str | None = None,
    publish_at: str | None = None,
) -> None:
    ensure_db()
    now = datetime.now().isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO today_tasks (
                task_date, topic_group, channel, title, source_topic, status, source, note,
                source_file, video_path, youtube_url, publish_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(task_date, topic_group, channel) DO UPDATE SET
                title=COALESCE(excluded.title, today_tasks.title),
                source_topic=COALESCE(excluded.source_topic, today_tasks.source_topic),
                status=excluded.status,
                source=excluded.source,
                note=COALESCE(excluded.note, today_tasks.note),
                source_file=COALESCE(excluded.source_file, today_tasks.source_file),
                video_path=COALESCE(excluded.video_path, today_tasks.video_path),
                youtube_url=COALESCE(excluded.youtube_url, today_tasks.youtube_url),
                publish_at=COALESCE(excluded.publish_at, today_tasks.publish_at),
                updated_at=excluded.updated_at
            """,
            (
                task_date,
                topic_group,
                channel,
                title,
                source_topic,
                status,
                source,
                note,
                source_file,
                video_path,
                youtube_url,
                publish_at,
                now,
            ),
        )


def mark_jobs(
    task_date: str,
    jobs: list[dict[str, Any]],
    *,
    status: str,
    source: str,
    note: str | None = None,
) -> int:
    count = 0
    for job in jobs:
        topic_group = str(job.get("topic_group") or job.get("topic") or "").strip()
        channel = str(job.get("channel") or "").strip()
        if not topic_group or not channel:
            continue
        upsert_task_status(
            task_date=task_date,
            topic_group=topic_group,
            channel=channel,
            status=status,
            title=str(job.get("title") or job.get("topic") or topic_group),
            source_topic=str(job.get("_llm_topic_override") or job.get("title") or job.get("topic") or topic_group),
            source=source,
            note=note,
            source_file=str(job.get("source_file") or job.get("day_file") or ""),
        )
        count += 1
    return count


def get_completed_keys(task_date: str) -> set[str]:
    ensure_db()
    placeholders = ",".join("?" for _ in COMPLETED_STATUSES)
    params: list[Any] = [task_date, *sorted(COMPLETED_STATUSES)]
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT topic_group, channel
            FROM today_tasks
            WHERE task_date = ?
              AND status IN ({placeholders})
            """,
            params,
        ).fetchall()
    return {f"{row['topic_group']}::{row['channel']}" for row in rows}


def list_task_history(
    *,
    search: str | None = None,
    channel: str | None = None,
    status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 300,
) -> list[dict[str, Any]]:
    ensure_db()
    where: list[str] = []
    params: list[Any] = []
    if search:
        where.append("(topic_group LIKE ? OR title LIKE ? OR source_topic LIKE ?)")
        needle = f"%{search}%"
        params.extend([needle, needle, needle])
    if channel:
        where.append("channel = ?")
        params.append(channel)
    if status:
        where.append("status = ?")
        params.append(status)
    if date_from:
        where.append("task_date >= ?")
        params.append(date_from)
    if date_to:
        where.append("task_date <= ?")
        params.append(date_to)

    sql = "SELECT * FROM today_tasks"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY task_date DESC, updated_at DESC LIMIT ?"
    params.append(max(1, min(int(limit), 1000)))

    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def list_reserved_publish_slots(
    *,
    channel: str | None = None,
    from_iso: str | None = None,
) -> list[dict[str, Any]]:
    """완료된 예약 업로드의 publish_at 목록을 반환한다."""
    ensure_db()
    placeholders = ",".join("?" for _ in COMPLETED_STATUSES)
    params: list[Any] = [*sorted(COMPLETED_STATUSES)]
    where = [f"status IN ({placeholders})", "publish_at IS NOT NULL", "publish_at != ''"]

    if channel:
        where.append("channel = ?")
        params.append(channel)
    if from_iso:
        where.append("publish_at >= ?")
        params.append(from_iso)

    sql = f"""
        SELECT task_date, topic_group, channel, publish_at
        FROM today_tasks
        WHERE {' AND '.join(where)}
        ORDER BY publish_at ASC
    """
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]
