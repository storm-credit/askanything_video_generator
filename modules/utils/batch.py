"""배치 생성 큐 — SQLite 기반 주제 큐 + 순차 생성 + 검수 워크플로우

여러 주제를 등록하면 순차적으로 생성하고 결과를 저장합니다.
야간 배치, 다국어 동시 생성 등에 활용.

상태 흐름:
  pending → running → draft → reviewed → approved → completed
                                                   → failed
  스크립트 수정 시: prompt_status → stale, fact_check_status → pending
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


def _ensure_column(conn, table: str, column: str, ddl: str):
    """테이블에 컬럼이 없으면 안전하게 추가합니다."""
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")


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
            camera_style TEXT DEFAULT 'auto',
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

    # 검수 워크플로우 컬럼 마이그레이션
    _ensure_column(conn, "batch_jobs", "script_version", "script_version INTEGER DEFAULT 1")
    _ensure_column(conn, "batch_jobs", "prompt_version", "prompt_version INTEGER DEFAULT 1")
    _ensure_column(conn, "batch_jobs", "fact_check_status", "fact_check_status TEXT DEFAULT 'pending'")
    _ensure_column(conn, "batch_jobs", "prompt_status", "prompt_status TEXT DEFAULT 'draft'")
    _ensure_column(conn, "batch_jobs", "stale_reason", "stale_reason TEXT")
    _ensure_column(conn, "batch_jobs", "review_notes", "review_notes TEXT")
    _ensure_column(conn, "batch_jobs", "reviewed_at", "reviewed_at TEXT")
    _ensure_column(conn, "batch_jobs", "approved_at", "approved_at TEXT")
    _ensure_column(conn, "batch_jobs", "channel_fit_score", "channel_fit_score INTEGER")
    _ensure_column(conn, "batch_jobs", "script_hash", "script_hash TEXT")
    _ensure_column(conn, "batch_jobs", "draft_title", "draft_title TEXT")
    _ensure_column(conn, "batch_jobs", "draft_tags", "draft_tags TEXT")
    _ensure_column(conn, "batch_jobs", "draft_cuts_json", "draft_cuts_json TEXT")

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
                "INSERT INTO batch_jobs (topic, language, camera_style, bgm_theme, llm_provider, video_engine, image_engine, channel, status, prompt_status, fact_check_status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft', 'draft', 'pending', ?)",
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
    ALLOWED_COLS = {
        "status", "video_path", "error", "started_at", "completed_at",
        "script_version", "prompt_version", "fact_check_status",
        "prompt_status", "stale_reason", "review_notes",
        "reviewed_at", "approved_at", "channel_fit_score", "script_hash",
        "draft_title", "draft_tags", "draft_cuts_json",
    }
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
            cur = conn.execute("DELETE FROM batch_jobs WHERE id = ? AND status IN ('pending', 'draft', 'completed', 'failed')", (job_id,))
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
    """다음 대기 중인 작업을 반환합니다 (pending 또는 draft)."""
    with _lock:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT * FROM batch_jobs WHERE status IN ('pending', 'draft') ORDER BY id LIMIT 1").fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def get_stats() -> dict:
    """큐 통계를 반환합니다 (상태별 + 검수 상태별)."""
    with _lock:
        conn = _get_conn()
        try:
            rows = conn.execute("SELECT status, COUNT(*) as cnt FROM batch_jobs GROUP BY status").fetchall()
            stats = {r["status"]: r["cnt"] for r in rows}
            # prompt_status 통계
            p_rows = conn.execute("SELECT prompt_status, COUNT(*) as cnt FROM batch_jobs GROUP BY prompt_status").fetchall()
            p_stats = {r["prompt_status"]: r["cnt"] for r in p_rows}
            # fact_check 통계
            f_rows = conn.execute("SELECT fact_check_status, COUNT(*) as cnt FROM batch_jobs GROUP BY fact_check_status").fetchall()
            f_stats = {r["fact_check_status"]: r["cnt"] for r in f_rows}
            return {
                "pending": stats.get("pending", 0),
                "running": stats.get("running", 0),
                "draft": stats.get("draft", 0),
                "reviewed": stats.get("reviewed", 0),
                "approved": stats.get("approved", 0),
                "completed": stats.get("completed", 0),
                "failed": stats.get("failed", 0),
                "total": sum(stats.values()),
                "prompt_draft": p_stats.get("draft", 0),
                "prompt_stale": p_stats.get("stale", 0),
                "prompt_approved": p_stats.get("approved", 0),
                "fact_pending": f_stats.get("pending", 0),
                "fact_verified": f_stats.get("verified", 0),
                "fact_risky": f_stats.get("risky", 0),
            }
        finally:
            conn.close()


# ── 검수 워크플로우 헬퍼 ──────────────────────────────────

def mark_stale(job_id: int, reason: str = "script_updated") -> None:
    """스크립트 수정 시 프롬프트를 stale로 표시하고 팩트체크도 리셋 + 이미지 캐시 무효화."""
    update_job(job_id, prompt_status="stale", stale_reason=reason, fact_check_status="pending")
    # 이미지 캐시 무효화: draft_cuts_json에서 image_prompt 추출
    job = get_job(job_id)
    if job and job.get("draft_cuts_json"):
        try:
            from modules.utils.cache import invalidate_cache
            cuts = json.loads(job["draft_cuts_json"])
            for cut in cuts:
                img_prompt = cut.get("image_prompt") or cut.get("prompt", "")
                if img_prompt:
                    invalidate_cache(img_prompt)
        except Exception:
            pass  # 캐시 무효화 실패해도 상태는 이미 stale


def mark_reviewed(job_id: int, notes: str | None = None) -> None:
    """검토 완료 표시."""
    kwargs: dict[str, Any] = {
        "status": "reviewed",
        "reviewed_at": datetime.now().isoformat(),
    }
    if notes:
        kwargs["review_notes"] = notes
    update_job(job_id, **kwargs)


def mark_verified(job_id: int) -> None:
    """팩트체크 완료 표시."""
    update_job(job_id, fact_check_status="verified")


def mark_risky(job_id: int, notes: str | None = None) -> None:
    """팩트체크 위험 표시."""
    kwargs: dict[str, Any] = {"fact_check_status": "risky"}
    if notes:
        kwargs["review_notes"] = notes
    update_job(job_id, **kwargs)


def mark_approved(job_id: int) -> bool:
    """최종 승인 — 렌더 단계로 이동 가능. 이미 running/completed면 무시."""
    with _lock:
        conn = _get_conn()
        try:
            row = conn.execute("SELECT status FROM batch_jobs WHERE id = ?", (job_id,)).fetchone()
            if not row or row["status"] in ("running", "completed"):
                return False
            conn.execute(
                "UPDATE batch_jobs SET status = 'approved', prompt_status = 'approved', "
                "fact_check_status = 'verified', approved_at = ? WHERE id = ? AND status NOT IN ('running', 'completed')",
                (datetime.now().isoformat(), job_id),
            )
            conn.commit()
            return True
        finally:
            conn.close()


def _compute_hash(text: str) -> str:
    """스크립트 텍스트의 SHA-256 해시를 반환합니다."""
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def update_script(job_id: int, new_script_text: str) -> bool:
    """스크립트 수정 시 해시 비교 → 변경됐으면 자동 stale 처리.

    Returns: True if script actually changed, False if identical.
    """
    job = get_job(job_id)
    if not job:
        return False
    new_hash = _compute_hash(new_script_text)
    old_hash = job.get("script_hash")
    if old_hash == new_hash:
        return False  # 내용 동일 — stale 처리 불필요
    bump_script_version(job_id, new_hash=new_hash)
    return True


def bump_script_version(job_id: int, new_hash: str | None = None) -> None:
    """스크립트 수정 시 버전 올리고 프롬프트를 stale 처리 + 팩트체크 리셋."""
    job = get_job(job_id)
    if not job:
        return
    new_ver = (job.get("script_version") or 0) + 1
    kwargs: dict[str, Any] = {
        "script_version": new_ver,
        "prompt_status": "stale",
        "stale_reason": "script_updated",
        "fact_check_status": "pending",
    }
    if new_hash:
        kwargs["script_hash"] = new_hash
    update_job(job_id, **kwargs)


def bump_prompt_version(job_id: int) -> None:
    """프롬프트 재생성 시 버전 올리고 draft로 복귀."""
    job = get_job(job_id)
    if not job:
        return
    new_ver = (job.get("prompt_version") or 0) + 1
    update_job(job_id, prompt_version=new_ver, prompt_status="draft", stale_reason=None)
