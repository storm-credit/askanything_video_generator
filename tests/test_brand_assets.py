"""채널별 브랜드 에셋 해석 테스트 — 폴백 로직 검증"""
import os
import pytest
from unittest.mock import patch
from modules.video.remotion import _resolve_brand_asset


@pytest.fixture
def brand_dir(tmp_path):
    """테스트용 브랜드 디렉토리 구조 생성"""
    # brand/intro.png (기본)
    brand = tmp_path / "brand"
    brand.mkdir()
    (brand / "intro.png").write_bytes(b"default-intro")
    (brand / "outro.jpg").write_bytes(b"default-outro")

    # brand/channels/askanything/
    ch_ask = brand / "channels" / "askanything"
    ch_ask.mkdir(parents=True)
    (ch_ask / "intro.png").write_bytes(b"ask-intro")
    (ch_ask / "outro.jpg").write_bytes(b"ask-outro")

    # brand/channels/wonderdrop/ (intro만 있음)
    ch_wonder = brand / "channels" / "wonderdrop"
    ch_wonder.mkdir(parents=True)
    (ch_wonder / "intro.png").write_bytes(b"wonder-intro")
    # outro.jpg 없음 → 기본 폴백

    return str(brand)


class TestResolveBrandAsset:
    def test_channel_specific_intro(self, brand_dir):
        with patch("modules.video.remotion.BRAND_DIR", brand_dir), \
             patch("modules.video.remotion.CHANNELS_DIR", os.path.join(brand_dir, "channels")):
            result = _resolve_brand_asset("intro.png", channel="askanything")
            assert "askanything" in result and result.endswith("intro.png")

    def test_channel_specific_outro(self, brand_dir):
        with patch("modules.video.remotion.BRAND_DIR", brand_dir), \
             patch("modules.video.remotion.CHANNELS_DIR", os.path.join(brand_dir, "channels")):
            result = _resolve_brand_asset("outro.jpg", channel="askanything")
            assert "askanything" in result and result.endswith("outro.jpg")

    def test_channel_fallback_to_default(self, brand_dir):
        """채널 폴더에 파일 없으면 기본 사용"""
        with patch("modules.video.remotion.BRAND_DIR", brand_dir), \
             patch("modules.video.remotion.CHANNELS_DIR", os.path.join(brand_dir, "channels")):
            result = _resolve_brand_asset("outro.jpg", channel="wonderdrop")
            assert "wonderdrop" not in result
            assert result.endswith("outro.jpg")

    def test_no_channel_uses_default(self, brand_dir):
        with patch("modules.video.remotion.BRAND_DIR", brand_dir), \
             patch("modules.video.remotion.CHANNELS_DIR", os.path.join(brand_dir, "channels")):
            result = _resolve_brand_asset("intro.png", channel=None)
            assert "channels" not in result
            assert result.endswith("intro.png")

    def test_unknown_channel_uses_default(self, brand_dir):
        with patch("modules.video.remotion.BRAND_DIR", brand_dir), \
             patch("modules.video.remotion.CHANNELS_DIR", os.path.join(brand_dir, "channels")):
            result = _resolve_brand_asset("intro.png", channel="nonexistent")
            assert "channels" not in result
            assert result.endswith("intro.png")

    def test_nonexistent_asset(self, brand_dir):
        with patch("modules.video.remotion.BRAND_DIR", brand_dir), \
             patch("modules.video.remotion.CHANNELS_DIR", os.path.join(brand_dir, "channels")):
            result = _resolve_brand_asset("logo.svg", channel="askanything")
            assert result is None
