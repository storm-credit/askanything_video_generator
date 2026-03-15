"""스마트 썸네일 자동 추출 — Laplacian variance 기반 선명도 스코어링

참고: Pech-Pacheco et al. (2000) "Diatom autofocusing in brightfield microscopy"
Laplacian의 분산이 높을수록 이미지가 선명(blur 없음)합니다.
"""
import os
from PIL import Image


def _sharpness_score(image_path: str) -> float:
    """이미지의 선명도 점수를 계산합니다 (Laplacian variance 근사).

    PIL만 사용하는 경량 구현: 그레이스케일 변환 후 에지 검출 필터 적용.
    """
    try:
        img = Image.open(image_path).convert("L")  # 그레이스케일
        # Laplacian 커널 근사: PIL ImageFilter 사용
        from PIL import ImageFilter
        edges = img.filter(ImageFilter.Kernel(
            size=(3, 3),
            kernel=[0, 1, 0, 1, -4, 1, 0, 1, 0],
            scale=1,
            offset=128,
        ))
        # 분산 계산
        pixels = list(edges.getdata())
        mean = sum(pixels) / len(pixels)
        variance = sum((p - mean) ** 2 for p in pixels) / len(pixels)
        return variance
    except Exception:
        return 0.0


def select_best_thumbnail(image_paths: list[str]) -> str | None:
    """여러 이미지 중 가장 선명한 것을 썸네일로 선택합니다."""
    if not image_paths:
        return None

    valid = [(p, _sharpness_score(p)) for p in image_paths if os.path.exists(p)]
    if not valid:
        return None

    best_path, best_score = max(valid, key=lambda x: x[1])
    print(f"   [썸네일] 최적 이미지 선택: {os.path.basename(best_path)} (선명도: {best_score:.0f})")
    return best_path


def create_thumbnail(image_path: str, output_path: str, size: tuple[int, int] = (1280, 720)) -> str | None:
    """선택된 이미지에서 YouTube/TikTok 썸네일용 이미지를 생성합니다.

    1280x720 (16:9) 크롭 — 세로 이미지에서 중앙 영역 추출.
    """
    try:
        from PIL import ImageOps
        img = Image.open(image_path).convert("RGB")
        thumb = ImageOps.fit(img, size, method=Image.LANCZOS, centering=(0.5, 0.35))
        thumb.save(output_path, quality=95)
        print(f"   [썸네일] {size[0]}x{size[1]} 생성 완료: {os.path.basename(output_path)}")
        return output_path
    except Exception as e:
        print(f"[썸네일 경고] 생성 실패: {e}")
        return None
