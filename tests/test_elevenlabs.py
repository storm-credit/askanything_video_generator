"""ElevenLabs TTS 유틸리티 테스트"""
import os
import struct
import pytest
from modules.tts.elevenlabs import _backoff_delay, _write_silent_wav


class TestBackoffDelay:
    def test_returns_positive(self):
        for attempt in range(5):
            assert _backoff_delay(attempt) > 0

    def test_increases_with_attempt(self):
        """평균적으로 attempt가 클수록 delay가 길어야 함"""
        delays_0 = [_backoff_delay(0) for _ in range(20)]
        delays_3 = [_backoff_delay(3) for _ in range(20)]
        assert sum(delays_3) / len(delays_3) > sum(delays_0) / len(delays_0)

    def test_capped_at_reasonable_value(self):
        """최대 base=16 + jitter → 24 이하"""
        for _ in range(50):
            assert _backoff_delay(10) <= 24.0

    def test_includes_jitter(self):
        """같은 attempt에서 다른 값 나오는지 (지터 확인)"""
        values = {_backoff_delay(2) for _ in range(20)}
        assert len(values) > 1  # 모두 같으면 지터 없음


class TestWriteSilentWav:
    def test_creates_valid_wav(self, tmp_dir):
        path = os.path.join(tmp_dir, "silent.wav")
        _write_silent_wav(path, duration_sec=1.0)
        assert os.path.exists(path)
        size = os.path.getsize(path)
        assert size > 44  # WAV 헤더(44) + 데이터

    def test_wav_header(self, tmp_dir):
        path = os.path.join(tmp_dir, "test.wav")
        _write_silent_wav(path, duration_sec=0.5)
        with open(path, "rb") as f:
            assert f.read(4) == b"RIFF"
            f.read(4)  # file size
            assert f.read(4) == b"WAVE"

    def test_duration_affects_size(self, tmp_dir):
        short = os.path.join(tmp_dir, "short.wav")
        long = os.path.join(tmp_dir, "long.wav")
        _write_silent_wav(short, duration_sec=0.5)
        _write_silent_wav(long, duration_sec=2.0)
        assert os.path.getsize(long) > os.path.getsize(short)

    def test_custom_sample_rate(self, tmp_dir):
        path = os.path.join(tmp_dir, "custom.wav")
        _write_silent_wav(path, duration_sec=1.0, sample_rate=44100)
        # 44100 * 2 bytes * 1 sec + 44 header = 88244
        assert os.path.getsize(path) == 44 + 44100 * 2
