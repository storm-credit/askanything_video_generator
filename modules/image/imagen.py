import os
import time
from PIL import Image, ImageOps
import io

from modules.utils.keys import record_key_usage, mark_key_exhausted, get_google_key, mask_key
from modules.utils.constants import MASTER_STYLE, is_quota_error

MAX_KEY_RETRIES = 3  # 429 시 최대 키 전환 횟수


def generate_image_imagen(prompt, index, topic_folder="default_topic", api_key=None):
    """
    Google Imagen 4 API로 이미지를 생성합니다.
    429 에러 시 다른 키로 자동 전환하여 재시도합니다.
    """
    if not prompt or not prompt.strip():
        raise ValueError(f"[Imagen 이미지 오류] 프롬프트가 비어 있습니다 (index={index})")

    enhanced_prompt = MASTER_STYLE + prompt
    tried_keys: set[str] = set()
    current_key = api_key

    for key_attempt in range(MAX_KEY_RETRIES):
        # 키 선택 (이전에 429 난 키 제외)
        if key_attempt == 0:
            final_api_key = current_key or get_google_key(service="imagen")
        else:
            final_api_key = get_google_key(service="imagen", exclude=tried_keys)

        if not final_api_key:
            raise EnvironmentError("Google API 키가 제공되지 않았습니다. GEMINI_API_KEY를 설정하세요.")

        if final_api_key in tried_keys:
            raise RuntimeError(f"[Imagen 4] 컷 {index+1}: 사용 가능한 키 없음 ({len(tried_keys)}개 소진)")

        tried_keys.add(final_api_key)

        if key_attempt > 0:
            print(f"  [Imagen 4] 컷 {index+1} 다른 키로 재시도 (시도 {key_attempt+1}/{MAX_KEY_RETRIES}, 키: {mask_key(final_api_key)})")

        # 이미지 생성 재시도 (안전 정책 실패 등 일반 재시도)
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if attempt == 0 and key_attempt == 0:
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
                # 429 쿼터 초과 → 키 차단 후 다른 키로 전환
                if is_quota_error(error_msg):
                    mark_key_exhausted(final_api_key, "imagen")
                    print(f"  [Imagen 4 쿼터 초과] 컷 {index+1}: 키 차단됨 → 다른 키로 전환...")
                    break  # 내부 retry 루프 탈출 → 외부 key_attempt 루프로
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
        # break로 나왔으면 (429) → 다음 키로 계속

    raise RuntimeError(f"[Imagen 4] 컷 {index+1}: {MAX_KEY_RETRIES}개 키 모두 쿼터 초과")


def _generate_imagen(api_key, prompt):
    """google-genai SDK로 Imagen 4 이미지를 생성합니다."""
    from google import genai
    from google.genai import types

    model_name = os.getenv("IMAGEN_MODEL", "imagen-4.0-generate-001")
    safety_level = os.getenv("IMAGEN_SAFETY_FILTER", "BLOCK_MEDIUM_AND_ABOVE")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_images(
        model=model_name,
        prompt=prompt,
        config=types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="9:16",
            safety_filter_level=safety_level,
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
