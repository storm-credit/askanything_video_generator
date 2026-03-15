import os
import sys
import tempfile
import shutil
import pytest

# 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture
def tmp_dir():
    """임시 디렉토리 생성 후 테스트 종료 시 정리"""
    d = tempfile.mkdtemp(prefix="askanything_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def sample_image(tmp_dir):
    """테스트용 100x100 RGB 이미지 생성"""
    from PIL import Image
    path = os.path.join(tmp_dir, "sample.png")
    img = Image.new("RGB", (100, 100), color=(128, 64, 32))
    # 선명도 차이를 위한 패턴
    for x in range(0, 100, 2):
        for y in range(0, 100, 2):
            img.putpixel((x, y), (255, 255, 255))
    img.save(path)
    return path


@pytest.fixture
def blurry_image(tmp_dir):
    """테스트용 블러 이미지 (단색)"""
    from PIL import Image
    path = os.path.join(tmp_dir, "blurry.png")
    img = Image.new("RGB", (100, 100), color=(128, 128, 128))
    img.save(path)
    return path


@pytest.fixture
def sample_wav(tmp_dir):
    """테스트용 1초 무음 WAV 파일"""
    import struct
    path = os.path.join(tmp_dir, "sample.wav")
    sample_rate = 22050
    num_samples = sample_rate
    data_size = num_samples * 2
    with open(path, "wb") as f:
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + data_size))
        f.write(b"WAVEfmt ")
        f.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16))
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(b"\x00" * data_size)
    return path
