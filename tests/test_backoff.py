"""지수 백오프 + 지터 테스트 — 범위 검증"""
import pytest
from modules.tts.elevenlabs import _backoff_delay


class TestBackoffDelay:
    def test_attempt_0(self):
        """첫 시도: base=2, 범위 2~3초"""
        for _ in range(20):
            delay = _backoff_delay(0)
            assert 2.0 <= delay <= 3.0

    def test_attempt_1(self):
        """두번째 시도: base=4, 범위 4~6초"""
        for _ in range(20):
            delay = _backoff_delay(1)
            assert 4.0 <= delay <= 6.0

    def test_attempt_2(self):
        """세번째 시도: base=8, 범위 8~12초"""
        for _ in range(20):
            delay = _backoff_delay(2)
            assert 8.0 <= delay <= 12.0

    def test_cap_at_16(self):
        """cap: base=16, 범위 16~24초"""
        for _ in range(20):
            delay = _backoff_delay(10)
            assert 16.0 <= delay <= 24.0

    def test_always_positive(self):
        for attempt in range(10):
            assert _backoff_delay(attempt) > 0

    def test_jitter_varies(self):
        """지터: 같은 attempt라도 결과가 다름"""
        delays = {_backoff_delay(1) for _ in range(20)}
        assert len(delays) > 1  # 모두 같으면 지터가 없는 것
