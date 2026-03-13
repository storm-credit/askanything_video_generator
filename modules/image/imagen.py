import os
import time
from PIL import Image, ImageOps
import io

from modules.utils.keys import record_key_usage


def generate_image_imagen(prompt, index, topic_folder="default_topic", api_key=None):
    """Google Imagen 4 API로 이미지를 생성합니다."""
    final_api_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not final_api_key:
        raise EnvironmentError("Google API 키가 제공되지 않았습니다. GEMINI_API_KEY를 설정하세요.")

    if not prompt or not prompt.strip():
        raise ValueError(f"[Imagen 이미지 오류] 프롬프트가 비어 있습니다 (index={index})")

    # National Geographic 스타일 마스터 프리셋
    master_style = (
        "Award-winning cinematic photograph, National Geographic high-end documentary style, "
        "hyper-detailed, global illumination, bright vibrant uplifting lighting, "
        "breathtaking aesthetic, 8K resolution, vertical composition, family-friendly. "
        "Absolutely NO TEXT, NO LETTERS, NO WORDS, NO WATERMARKS. "
    )
    enhanced_prompt = master_style + prompt

    max_retries = 3
    for attempt in range(max_retries):
        try:
            if attempt == 0:
                print(f"-> [아트 디렉터] 컷 {index+1} Imagen 4 렌더링 중...")

            image_bytes = _generate_imagen(final_api_key, enhanced_prompt)

            if not image_bytes:
                raise ValueError("이미지 생성 결과가 비어 있습니다.")

            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            target_size = (1080, 1920)
            fitted_image = ImageOps.fit(image, target_size, method=Image.LANCZOS, centering=(0.5, 0.5))

            image_dir = f"assets/{topic_folder}/images"
            os.makedirs(image_dir, exist_ok=True)
            filename = os.path.join(image_dir, f"cut_{index:02}.png")
            fitted_image.save(filename)

            record_key_usage(final_api_key, "imagen")
            print(f"OK [아트 디렉터] 컷 {index+1} Imagen 4 렌더링 완료!")
            return filename

        except Exception as e:
            error_msg = str(e)
            if attempt < max_retries - 1:
                if "safety" in error_msg.lower() or "blocked" in error_msg.lower() or "SAFETY" in error_msg:
                    enhanced_prompt = (
                        "A safe, beautiful abstract cinematic visualization, "
                        "National Geographic documentary style, atmospheric lighting, "
                        "bright and uplifting, vertical composition, NO TEXT, NO LETTERS."
                    )
                    print(f"  [Imagen 4 경고] 컷 {index+1} 안전 정책 위반. 대체 프롬프트로 재시도 ({attempt+1}/{max_retries})")
                else:
                    print(f"  [Imagen 4 경고] 컷 {index+1} 실패. 3초 후 재시도 ({attempt+1}/{max_retries}) | {e}")
                time.sleep(3)
            else:
                raise RuntimeError(f"[Imagen 4 이미지 생성 최종 실패] index={index}: {e}")


def _generate_imagen(api_key, prompt):
    """google-genai SDK로 Imagen 4 이미지를 생성합니다."""
    from google import genai
    from google.genai import types

    model_name = os.getenv("IMAGEN_MODEL", "imagen-4.0-generate-001")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_images(
        model=model_name,
        prompt=prompt,
        config=types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="9:16",
            safety_filter_level="BLOCK_LOW_AND_ABOVE",
        ),
    )

    if not response.generated_images:
        raise ValueError("Imagen API 응답에 이미지가 없습니다.")

    gen_image = response.generated_images[0].image

    # google-genai SDK: image.image_bytes 속성으로 바이트 추출
    if hasattr(gen_image, "image_bytes") and gen_image.image_bytes:
        return gen_image.image_bytes

    # 대체: PIL 이미지로 변환
    if hasattr(gen_image, "_pil_image") and gen_image._pil_image:
        buf = io.BytesIO()
        gen_image._pil_image.save(buf, format="PNG")
        return buf.getvalue()

    raise ValueError("Imagen API 이미지 데이터를 추출할 수 없습니다.")
