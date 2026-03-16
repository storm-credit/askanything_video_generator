"""배치 생성 큐 — SQLite 기반 주제 큐 + 순차 생성

여러 주제를 등록하면 순차적으로 생성하고 결과를 저장합니다.
야간 배치, 다국어 동시 생성 등에 활용.
"""
import os
import json
import sqlite3
import time
import threading
from datetime import datetime
from typing import Any

DB_PATH = os.path.join("assets", "batch_queue.db")
_lock = threading.Lock()
_db_initialized = False


def _init_db():
    global _db_initialized
    if _db_initialized:
        return
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS batch_jobs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            language TEXT DEFAULT 'ko',
            camera_style TEXT DEFAULT 'dynamic',
            bgm_theme TEXT DEFAULT 'random',
            llm_provider TEXT DEFAULT 'gemini',
            video_engine TEXT DEFAULT 'veo3',
            image_engine TEXT DEFAULT 'imagen',
            channel TEXT,
            status TEXT DEFAULT 'pending',
            video_path TEXT,
            error TEXT,
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT
        )
    """)
    conn.commit()
    conn.close()
    _db_initialized = True


def _get_conn() -> sqlite3.Connection:
    _init_db()
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def has_duplicate_topic(topic: str) -> bool:
    """pending/running 상태에서 동일 주제가 이미 존재하는지 확인합니다."""
    with _lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM batch_jobs WHERE topic = ? AND status IN ('pending', 'running')",
                (topic,),
            ).fetchone()
            return row["cnt"] > 0
        finally:
            conn.close()


def add_job(topic: str, language: str = "ko", camera_style: str = "dynamic",
            bgm_theme: str = "random", llm_provider: str = "gemini",
            video_engine: str = "veo3", image_engine: str = "imagen",
            channel: str | None = None) -> int:
    """큐에 생성 작업을 추가합니다. 중복 주제 경고 후 작업 ID를 반환합니다."""
    with _lock:
        conn = _get_conn()
        try:
            # Duplicate check inside lock to prevent TOCTOU race
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM batch_jobs WHERE topic = ? AND status IN ('pending', 'running')",
                (topic,),
            ).fetchone()
            if row["cnt"] > 0:
                print(f"[배치 경고] 동일 주제가 이미 큐에 있습니다: {topic[:30]}...")
            cur = conn.execute(
                "INSERT INTO batch_jobs (topic, language, camera_style, bgm_theme, llm_provider, video_engine, image_engine, channel, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (topic, language, camera_style, bgm_theme, llm_provider, video_engine, image_engine, channel, datetime.now().isoformat()),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def add_jobs_bulk(topics: list[dict[str, Any]]) -> list[int]:
    """여러 작업을 한번에 추가합니다. 각 dict에 topic(필수) + 옵션 필드."""
    ids = []
    for t in topics:
        job_id = add_job(
            topic=t["topic"],
            language=t.get("language", "ko"),
            camera_style=t.get("cameraStyle", "dynamic"),
            bgm_theme=t.get("bgmTheme", "random"),
            llm_provider=t.get("llmProvider", "gemini"),
            video_engine=t.get("videoEngine", "veo3"),
            image_engine=t.get("imageEngine", "imagen"),
            channel=t.get("channel"),
        )
        ids.append(job_id)
    return ids


def get_queue() -> list[dict]:
    """큐의 모든 작업을 반환합니다."""
    with _lock:
        conn = _get_conn()
        try:
            rows = conn.execute("SELECT * FROM batch_jobs ORDER BY id").fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def get_job(job_id: int) -> dict | None:
    with _lock:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM batch_jobs WHERE id = ?", (job_id,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def update_job(job_id: int, **kwargs) -> None:
    ALLOWED_COLS = {"status", "video_path", "error", "started_at", "completed_at"}
    invalid = set(kwargs.keys()) - ALLOWED_COLS
    if invalid:
        raise ValueError(f"Invalid columns: {invalid}")
    with _lock:
        conn = _get_conn()
        try:
            sets = ", ".join(f"{k} = ?" for k in kwargs)
            conn.execute(f"UPDATE batch_jobs SET {sets} WHERE id = ?", (*kwargs.values(), job_id))
            conn.commit()
        finally:
            conn.close()


def delete_job(job_id: int) -> bool:
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.execute("DELETE FROM batch_jobs WHERE id = ? AND status IN ('pending', 'completed', 'failed')", (job_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def clear_completed() -> int:
    """완료/실패 작업을 모두 제거합니다."""
    with _lock:
        conn = _get_conn()
        try:
            cur = conn.execute("DELETE FROM batch_jobs WHERE status IN ('completed', 'failed')")
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()


def get_next_pending() -> dict | None:
    """다음 대기 중인 작업을 반환합니다."""
    with _lock:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM batch_jobs WHERE status = 'pending' ORDER BY id LIMIT 1").fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def get_stats() -> dict:
    """큐 통계를 반환합니다."""
    with _lock:
        conn = _get_conn()
        try:
            rows = conn.execute("SELECT status, COUNT(*) as cnt FROM batch_jobs GROUP BY status").fetchall()
            stats = {r["status"]: r["cnt"] for r in rows}
            return {
                "pending": stats.get("pending", 0),
                "running": stats.get("running", 0),
                "completed": stats.get("completed", 0),
                "failed": stats.get("failed", 0),
                "total": sum(stats.values()),
            }
        finally:
            conn.close()
