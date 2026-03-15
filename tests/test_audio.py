"""오디오 정규화 유닛 테스트 — 엣지케이스 처리"""
import os
import struct
import pytest
import tempfile
from modules.utils.audio import normalize_audio_lufs


def _create_wav(path: str, duration_sec: float = 0.5, sample_rate: int = 22050, silent: bool = False):
    """테스트용 WAV 파일 생성"""
    import math
    num_samples = int(sample_rate * duration_sec)
    data_size = num_samples * 2
    with open(path, "wb") as f:
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + data_size))
        f.write(b"WAVEfmt ")
        f.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16))
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        if silent:
            f.write(b"\x00" * data_size)
        else:
            for i in range(num_samples):
                val = int(16000 * math.sin(2 * math.pi * 440 * i / sample_rate))
                f.write(struct.pack("<h", val))


class TestNormalizeAudioLufs:
    def test_nonexistent_file(self):
        result = normalize_audio_lufs("/nonexistent/audio.wav")
        assert result == "/nonexistent/audio.wav"

    def test_none_path(self):
        result = normalize_audio_lufs(None)
        assert result is None

    def test_empty_string(self):
        result = normalize_audio_lufs("")
        assert result == ""

    def test_empty_file(self, tmp_path):
        path = str(tmp_path / "empty.wav")
        with open(path, "wb") as f:
            pass  # 0 bytes
        result = normalize_audio_lufs(path)
        assert result == path  # 빈 파일은 건너뜀

    def test_silent_wav_skipped(self, tmp_path):
        """무음 WAV는 정규화 건너뛰기 (-70 LUFS 이하)"""
        path = str(tmp_path / "silent.wav")
        _create_wav(path, silent=True)
        result = normalize_audio_lufs(path)
        assert result == path
        assert os.path.exists(path)

    def test_normal_wav_processed(self, tmp_path):
        """일반 WAV는 정규화 처리"""
        path = str(tmp_path / "tone.wav")
        _create_wav(path, duration_sec=1.0, silent=False)
        original_size = os.path.getsize(path)
        result = normalize_audio_lufs(path)
        assert result == path
        assert os.path.exists(path)
        assert os.path.getsize(path) > 0
