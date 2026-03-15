"""썸네일 유틸리티 테스트 — _sharpness_score, select_best_thumbnail, create_thumbnail"""
import os
import pytest
from PIL import Image
from modules.utils.thumbnail import _sharpness_score, select_best_thumbnail, create_thumbnail


class TestSharpnessScore:
    def test_sharp_image_higher_score(self, sample_image, blurry_image):
        sharp = _sharpness_score(sample_image)
        blurry = _sharpness_score(blurry_image)
        assert sharp > blurry

    def test_blurry_image_low_score(self, blurry_image):
        score = _sharpness_score(blurry_image)
        assert score >= 0

    def test_nonexistent_file_returns_zero(self):
        assert _sharpness_score("/nonexistent/path.png") == 0.0

    def test_returns_float(self, sample_image):
        assert isinstance(_sharpness_score(sample_image), float)


class TestSelectBestThumbnail:
    def test_selects_sharpest(self, sample_image, blurry_image):
        result = select_best_thumbnail([blurry_image, sample_image])
        assert result == sample_image

    def test_empty_list_returns_none(self):
        assert select_best_thumbnail([]) is None

    def test_nonexistent_files_returns_none(self):
        assert select_best_thumbnail(["/fake/a.png", "/fake/b.png"]) is None

    def test_single_image(self, sample_image):
        assert select_best_thumbnail([sample_image]) == sample_image

    def test_mixed_valid_invalid(self, sample_image):
        result = select_best_thumbnail(["/fake.png", sample_image])
        assert result == sample_image


class TestCreateThumbnail:
    def test_creates_thumbnail(self, sample_image, tmp_dir):
        out = os.path.join(tmp_dir, "thumb.jpg")
        result = create_thumbnail(sample_image, out)
        assert result == out
        assert os.path.exists(out)
        img = Image.open(out)
        assert img.size == (1280, 720)

    def test_custom_size(self, sample_image, tmp_dir):
        out = os.path.join(tmp_dir, "thumb_custom.jpg")
        result = create_thumbnail(sample_image, out, size=(640, 360))
        assert result == out
        img = Image.open(out)
        assert img.size == (640, 360)

    def test_nonexistent_source_returns_none(self, tmp_dir):
        out = os.path.join(tmp_dir, "thumb.jpg")
        assert create_thumbnail("/fake.png", out) is None
