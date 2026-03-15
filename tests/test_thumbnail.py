"""스마트 썸네일 유닛 테스트 — 선명도 스코어링 + 선택 로직"""
import os
import pytest
import tempfile
from PIL import Image
from modules.utils.thumbnail import _sharpness_score, select_best_thumbnail, create_thumbnail


@pytest.fixture
def sharp_image(tmp_path):
    """선명한 이미지 (고대비 패턴)"""
    img = Image.new("L", (100, 100), 0)
    pixels = img.load()
    for x in range(100):
        for y in range(100):
            pixels[x, y] = 255 if (x + y) % 2 == 0 else 0
    path = str(tmp_path / "sharp.png")
    img.save(path)
    return path


@pytest.fixture
def blurry_image(tmp_path):
    """흐린 이미지 (단색)"""
    img = Image.new("L", (100, 100), 128)
    path = str(tmp_path / "blurry.png")
    img.save(path)
    return path


class TestSharpnessScore:
    def test_sharp_higher_than_blurry(self, sharp_image, blurry_image):
        sharp_score = _sharpness_score(sharp_image)
        blurry_score = _sharpness_score(blurry_image)
        assert sharp_score > blurry_score

    def test_nonexistent_file(self):
        assert _sharpness_score("/nonexistent/file.png") == 0.0

    def test_score_is_positive(self, sharp_image):
        assert _sharpness_score(sharp_image) > 0


class TestSelectBestThumbnail:
    def test_selects_sharpest(self, sharp_image, blurry_image):
        result = select_best_thumbnail([blurry_image, sharp_image])
        assert result == sharp_image

    def test_empty_list(self):
        assert select_best_thumbnail([]) is None

    def test_nonexistent_files(self):
        assert select_best_thumbnail(["/fake/a.png", "/fake/b.png"]) is None

    def test_single_image(self, sharp_image):
        assert select_best_thumbnail([sharp_image]) == sharp_image

    def test_mixed_existing_nonexisting(self, sharp_image):
        result = select_best_thumbnail(["/fake/x.png", sharp_image])
        assert result == sharp_image


class TestCreateThumbnail:
    def test_creates_thumbnail(self, sharp_image, tmp_path):
        output = str(tmp_path / "thumb.jpg")
        result = create_thumbnail(sharp_image, output, size=(320, 180))
        assert result == output
        assert os.path.exists(output)
        thumb = Image.open(output)
        assert thumb.size == (320, 180)

    def test_nonexistent_source(self, tmp_path):
        output = str(tmp_path / "thumb.jpg")
        result = create_thumbnail("/fake/image.png", output)
        assert result is None
