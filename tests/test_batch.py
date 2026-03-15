"""배치 큐 CRUD 테스트 — SQLite 기반"""
import os
import pytest
from unittest.mock import patch

# DB 경로를 임시 디렉토리로 리다이렉트
@pytest.fixture(autouse=True)
def temp_db(tmp_dir):
    db_path = os.path.join(tmp_dir, "test_batch.db")
    with patch("modules.utils.batch.DB_PATH", db_path):
        yield db_path


from modules.utils.batch import (
    add_job, add_jobs_bulk, get_queue, get_job,
    update_job, delete_job, clear_completed,
    get_next_pending, get_stats,
)


class TestAddJob:
    def test_add_single(self):
        job_id = add_job("블랙홀 탐험")
        assert isinstance(job_id, int)
        assert job_id >= 1

    def test_add_with_options(self):
        job_id = add_job("AI 기술", language="en", camera_style="gentle",
                         channel="wonderdrop")
        job = get_job(job_id)
        assert job["topic"] == "AI 기술"
        assert job["language"] == "en"
        assert job["camera_style"] == "gentle"
        assert job["channel"] == "wonderdrop"
        assert job["status"] == "pending"

    def test_add_increments_id(self):
        id1 = add_job("topic1")
        id2 = add_job("topic2")
        assert id2 > id1


class TestAddJobsBulk:
    def test_bulk_add(self):
        ids = add_jobs_bulk([
            {"topic": "주제1"},
            {"topic": "주제2", "language": "en"},
            {"topic": "주제3", "cameraStyle": "static"},
        ])
        assert len(ids) == 3
        assert all(isinstance(i, int) for i in ids)

    def test_bulk_empty(self):
        assert add_jobs_bulk([]) == []


class TestGetQueue:
    def test_returns_all(self):
        add_job("a")
        add_job("b")
        queue = get_queue()
        assert len(queue) >= 2

    def test_ordered_by_id(self):
        id1 = add_job("first")
        id2 = add_job("second")
        queue = get_queue()
        ids = [j["id"] for j in queue]
        assert ids.index(id1) < ids.index(id2)


class TestGetJob:
    def test_existing(self):
        job_id = add_job("test topic")
        job = get_job(job_id)
        assert job is not None
        assert job["topic"] == "test topic"

    def test_nonexistent(self):
        assert get_job(99999) is None


class TestUpdateJob:
    def test_update_status(self):
        job_id = add_job("update test")
        update_job(job_id, status="running")
        job = get_job(job_id)
        assert job["status"] == "running"

    def test_update_multiple_fields(self):
        job_id = add_job("multi update")
        update_job(job_id, status="completed", video_path="/out/video.mp4")
        job = get_job(job_id)
        assert job["status"] == "completed"
        assert job["video_path"] == "/out/video.mp4"


class TestDeleteJob:
    def test_delete_pending(self):
        job_id = add_job("to delete")
        assert delete_job(job_id) is True
        assert get_job(job_id) is None

    def test_delete_running_blocked(self):
        job_id = add_job("running job")
        update_job(job_id, status="running")
        assert delete_job(job_id) is False

    def test_delete_nonexistent(self):
        assert delete_job(99999) is False


class TestClearCompleted:
    def test_clears_completed_and_failed(self):
        id1 = add_job("done")
        id2 = add_job("fail")
        id3 = add_job("still pending")
        update_job(id1, status="completed")
        update_job(id2, status="failed")
        cleared = clear_completed()
        assert cleared == 2
        assert get_job(id1) is None
        assert get_job(id2) is None
        assert get_job(id3) is not None


class TestGetNextPending:
    def test_returns_oldest_pending(self):
        id1 = add_job("first pending")
        add_job("second pending")
        result = get_next_pending()
        assert result["id"] == id1

    def test_skips_non_pending(self):
        id1 = add_job("running")
        update_job(id1, status="running")
        id2 = add_job("pending")
        result = get_next_pending()
        assert result["id"] == id2

    def test_empty_queue(self):
        assert get_next_pending() is None


class TestGetStats:
    def test_stats_structure(self):
        stats = get_stats()
        assert "pending" in stats
        assert "running" in stats
        assert "completed" in stats
        assert "failed" in stats
        assert "total" in stats

    def test_stats_counts(self):
        add_job("a")
        add_job("b")
        id3 = add_job("c")
        update_job(id3, status="completed")
        stats = get_stats()
        assert stats["pending"] >= 2
        assert stats["completed"] >= 1
        assert stats["total"] >= 3
