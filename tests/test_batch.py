"""배치 큐 CRUD 테스트 — SQLite 기반"""
import os
import pytest
import tempfile
from unittest.mock import patch


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    """테스트마다 임시 DB 사용"""
    db_path = str(tmp_path / "test_batch.db")
    with patch("modules.utils.batch.DB_PATH", db_path):
        yield db_path


class TestBatchQueue:
    def test_add_job(self):
        from modules.utils.batch import add_job, get_job
        job_id = add_job("블랙홀 테스트")
        assert job_id > 0

        job = get_job(job_id)
        assert job is not None
        assert job["topic"] == "블랙홀 테스트"
        assert job["status"] == "pending"
        assert job["language"] == "ko"

    def test_add_job_with_channel(self):
        from modules.utils.batch import add_job, get_job
        job_id = add_job("테스트", channel="wonderdrop")
        job = get_job(job_id)
        assert job["channel"] == "wonderdrop"

    def test_add_job_custom_options(self):
        from modules.utils.batch import add_job, get_job
        job_id = add_job("test", language="en", camera_style="gentle",
                         llm_provider="openai", video_engine="kling")
        job = get_job(job_id)
        assert job["language"] == "en"
        assert job["camera_style"] == "gentle"
        assert job["llm_provider"] == "openai"
        assert job["video_engine"] == "kling"

    def test_get_nonexistent_job(self):
        from modules.utils.batch import get_job
        assert get_job(99999) is None

    def test_get_queue(self):
        from modules.utils.batch import add_job, get_queue
        add_job("주제1")
        add_job("주제2")
        add_job("주제3")
        queue = get_queue()
        assert len(queue) == 3
        assert queue[0]["topic"] == "주제1"

    def test_update_job(self):
        from modules.utils.batch import add_job, get_job, update_job
        job_id = add_job("업데이트 테스트")
        update_job(job_id, status="running", started_at="2026-01-01T00:00:00")
        job = get_job(job_id)
        assert job["status"] == "running"
        assert job["started_at"] == "2026-01-01T00:00:00"

    def test_delete_pending_job(self):
        from modules.utils.batch import add_job, delete_job, get_job
        job_id = add_job("삭제 테스트")
        assert delete_job(job_id) is True
        assert get_job(job_id) is None

    def test_delete_running_job_fails(self):
        from modules.utils.batch import add_job, update_job, delete_job, get_job
        job_id = add_job("실행 중")
        update_job(job_id, status="running")
        assert delete_job(job_id) is False
        assert get_job(job_id) is not None

    def test_clear_completed(self):
        from modules.utils.batch import add_job, update_job, clear_completed, get_queue
        id1 = add_job("완료됨")
        id2 = add_job("실패함")
        id3 = add_job("대기 중")
        update_job(id1, status="completed")
        update_job(id2, status="failed")

        cleared = clear_completed()
        assert cleared == 2
        queue = get_queue()
        assert len(queue) == 1
        assert queue[0]["topic"] == "대기 중"

    def test_get_next_pending(self):
        from modules.utils.batch import add_job, update_job, get_next_pending
        id1 = add_job("첫번째")
        id2 = add_job("두번째")
        update_job(id1, status="completed")

        next_job = get_next_pending()
        assert next_job is not None
        assert next_job["topic"] == "두번째"

    def test_get_next_pending_empty(self):
        from modules.utils.batch import get_next_pending
        assert get_next_pending() is None

    def test_get_stats(self):
        from modules.utils.batch import add_job, update_job, get_stats
        add_job("a")
        add_job("b")
        id3 = add_job("c")
        update_job(id3, status="completed")

        stats = get_stats()
        assert stats["pending"] == 2
        assert stats["completed"] == 1
        assert stats["total"] == 3

    def test_add_jobs_bulk(self):
        from modules.utils.batch import add_jobs_bulk, get_queue
        topics = [
            {"topic": "벌크1", "language": "en"},
            {"topic": "벌크2", "channel": "askanything"},
            {"topic": "벌크3"},
        ]
        ids = add_jobs_bulk(topics)
        assert len(ids) == 3
        queue = get_queue()
        assert len(queue) == 3
