"""오디오 정규화 유틸리티 테스트"""
import os
import pytest
from modules.utils.audio import normalize_audio_lufs, TARGET_LUFS


class TestNormalizeAudioLufs:
    def test_returns_path_for_nonexistent(self):
        result = normalize_audio_lufs("/nonexistent/audio.wav")
        assert result == "/nonexistent/audio.wav"

    def test_returns_path_for_none(self):
        assert normalize_audio_lufs(None) is None

    def test_returns_path_for_empty_string(self):
        assert normalize_audio_lufs("") == ""

    def test_returns_path_for_empty_file(self, tmp_dir):
        path = os.path.join(tmp_dir, "empty.wav")
        open(path, "w").close()
        result = normalize_audio_lufs(path)
        assert result == path

    def test_target_lufs_default(self):
        assert TARGET_LUFS == -14.0

    def test_silent_wav_skips_normalization(self, sample_wav):
        """무음 파일은 -70 LUFS 이하 → 정규화 건너뜀"""
        result = normalize_audio_lufs(sample_wav)
        assert result == sample_wav
        assert os.path.exists(result)
