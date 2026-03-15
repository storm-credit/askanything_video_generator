"""remotion.py 유틸리티 함수 테스트"""
import os
import pytest
from unittest.mock import patch
from modules.video.remotion import (
    _to_relative, _resolve_brand_asset, _validate_inputs,
    _select_bgm,
)


class TestToRelative:
    def test_assets_prefix(self):
        assert _to_relative("assets/test/video/out.mp4") == "test/video/out.mp4"

    def test_full_path(self):
        result = _to_relative(r"C:\project\assets\audio\cut_01.mp3")
        assert result == "audio/cut_01.mp3"

    def test_no_assets_in_path(self):
        assert _to_relative("some/other/path.mp4") == "some/other/path.mp4"

    def test_backslash_normalized(self):
        result = _to_relative("assets\test\file.mp3")
        assert "\\" not in result


class TestResolveBrandAsset:
    def test_channel_asset_exists(self, tmp_dir):
        ch_dir = os.path.join(tmp_dir, "channels", "mych")
        os.makedirs(ch_dir)
        asset = os.path.join(ch_dir, "intro.png")
        open(asset, "w").close()

        with patch("modules.video.remotion.CHANNELS_DIR", os.path.join(tmp_dir, "channels")):
            with patch("modules.video.remotion.BRAND_DIR", tmp_dir):
                result = _resolve_brand_asset("intro.png", channel="mych")
                assert result == asset

    def test_fallback_to_default(self, tmp_dir):
        default_asset = os.path.join(tmp_dir, "intro.png")
        open(default_asset, "w").close()

        with patch("modules.video.remotion.CHANNELS_DIR", os.path.join(tmp_dir, "channels")):
            with patch("modules.video.remotion.BRAND_DIR", tmp_dir):
                result = _resolve_brand_asset("intro.png", channel="nonexistent")
                assert result == default_asset

    def test_no_channel_uses_default(self, tmp_dir):
        default_asset = os.path.join(tmp_dir, "outro.jpg")
        open(default_asset, "w").close()

        with patch("modules.video.remotion.BRAND_DIR", tmp_dir):
            result = _resolve_brand_asset("outro.jpg", channel=None)
            assert result == default_asset

    def test_no_asset_returns_none(self, tmp_dir):
        with patch("modules.video.remotion.BRAND_DIR", tmp_dir):
            with patch("modules.video.remotion.CHANNELS_DIR", os.path.join(tmp_dir, "channels")):
                assert _resolve_brand_asset("missing.png") is None


class TestValidateInputs:
    def test_valid_inputs(self, sample_image, sample_wav):
        _validate_inputs([sample_image], [sample_wav], ["script"], [[]])

    def test_mismatched_lengths(self, sample_image, sample_wav):
        with pytest.raises(ValueError, match="길이"):
            _validate_inputs([sample_image, sample_image], [sample_wav], ["s"], [[]])

    def test_missing_visual(self, sample_wav):
        with pytest.raises(FileNotFoundError, match="visual"):
            _validate_inputs(["/fake.png"], [sample_wav], ["s"], [[]])

    def test_missing_audio(self, sample_image):
        with pytest.raises(FileNotFoundError, match="audio"):
            _validate_inputs([sample_image], ["/fake.wav"], ["s"], [[]])


class TestSelectBgm:
    def test_none_theme(self):
        assert _select_bgm("none") is None

    def test_bgm_dir_with_files(self, tmp_dir):
        bgm_dir = os.path.join(tmp_dir, "bgm")
        os.makedirs(bgm_dir)
        for name in ["epic.mp3", "calm.mp3"]:
            open(os.path.join(bgm_dir, name), "w").close()

        with patch("modules.video.remotion.BRAND_DIR", tmp_dir):
            result = _select_bgm("epic")
            assert result is not None
            assert "epic.mp3" in result

    def test_bgm_random(self, tmp_dir):
        bgm_dir = os.path.join(tmp_dir, "bgm")
        os.makedirs(bgm_dir)
        open(os.path.join(bgm_dir, "a.mp3"), "w").close()

        with patch("modules.video.remotion.BRAND_DIR", tmp_dir):
            result = _select_bgm("random")
            assert result is not None

    def test_single_bgm_fallback(self, tmp_dir):
        bgm_file = os.path.join(tmp_dir, "bgm.mp3")
        open(bgm_file, "w").close()

        with patch("modules.video.remotion.BRAND_DIR", tmp_dir):
            result = _select_bgm("random")
            assert result == bgm_file

    def test_no_bgm_returns_none(self, tmp_dir):
        with patch("modules.video.remotion.BRAND_DIR", tmp_dir):
            assert _select_bgm("random") is None
