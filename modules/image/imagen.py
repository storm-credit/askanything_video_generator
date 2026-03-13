import os
import time
from PIL import Image, ImageOps
import io

from modules.utils.keys import record_key_usage, mark_key_exhausted, get_google_key, mask_key
from modules.utils.constants import MASTER_STYLE, is_key_rotation_error
from modules.utils.models import get_model_chain, get_service_tag

MAX_KEY_RETRIES = 10  # 키 전환 최대 횟수 (무료 키 다수 → 유료 키 도달까지)


def generate_image_imagen(prompt, index, topic_folder="default_topic", api_key=None):
    """
    Google Imagen 4 API로 이미지를 생성합니다.
    429 에러 시 다른 키로 자동 전환, 전 키 소진 시 Fast 모델로 자동 폴백.
    """
    if not prompt or not prompt.strip():
        raise ValueError(f"[Imagen 이미지 오류] 프롬프트가 비어 있습니다 (index={index})")

    # 모델 체인: 환경변수 오버라이드 시 단일 모델, 아니면 Standard → Fast
    override_model = os.getenv("IMAGEN_MODEL")
    if override_model:
        model_chain = [{"id": override_model, "tag": "override", "label": override_model}]
    else:
        model_chain = get_model_chain("imagen")
        if not model_chain:
            model_chain = [{"id": "imagen-4.0-generate-001", "tag": "standard", "label": "Imagen 4"}]

    for model_idx, model in enumerate(model_chain):
        model_id = model["id"]
        model_label = model["label"]
        service_tag = get_service_tag("imagen", model_id)

        # 모델 체인 반복마다 프롬프트 초기화 (safety 폴백으로 변경된 프롬프트 리셋)
        enhanced_prompt = MASTER_STYLE + prompt

        tried_keys: set[str] = set()
        current_key = api_key

        for key_attempt in range(MAX_KEY_RETRIES):
            # 키 선택 (이전에 429 난 키 제외)
            if key_attempt == 0:
                final_api_key = current_key or get_google_key(service=service_tag)
            else:
                final_api_key = get_google_key(service=service_tag, exclude=tried_keys)

            if not final_api_key:
                break  # 이 모델에 사용 가능한 키 없음 → 다음 모델로

            if final_api_key in tried_keys:
                break  # 새 키 없음 → 다음 모델로

            tried_keys.add(final_api_key)

            if key_attempt > 0:
                print(f"  [{model_label}] 컷 {index+1} 다른 키로 재시도 (시도 {key_attempt+1}/{MAX_KEY_RETRIES}, 키: {mask_key(final_api_key)})")

            # 이미지 생성 재시도 (안전 정책 실패 등 일반 재시도)
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    if attempt == 0 and key_attempt == 0:
                        if model_idx == 0:
                            print(f"-> [아트 디렉터] 컷 {index+1} {model_label} 렌더링 중...")
                        else:
                            print(f"-> [아트 디렉터] 컷 {index+1} {model_label}로 폴백 렌더링 중...")

                    image_bytes = _generate_imagen(final_api_key, enhanced_prompt, model_id)

                    if not image_bytes:
                        raise ValueError("이미지 생성 결과가 비어 있습니다.")

                    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                    target_size = (1080, 1920)
                    fitted_image = ImageOps.fit(image, target_size, method=Image.LANCZOS, centering=(0.5, 0.5))

                    image_dir = f"assets/{topic_folder}/images"
                    os.makedirs(image_dir, exist_ok=True)
                    filename = os.path.join(image_dir, f"cut_{index:02}.png")
                    fitted_image.save(filename)

                    record_key_usage(final_api_key, service_tag)
                    print(f"OK [아트 디렉터] 컷 {index+1} {model_label} 렌더링 완료!")
                    return filename

                except Exception as e:
                    error_msg = str(e)
                    # 429/503/유료전용 → 키 차단 후 다른 키로 전환
                    if is_key_rotation_error(error_msg):
                        mark_key_exhausted(final_api_key, service_tag)
                        print(f"  [{model_label} 키 전환] 컷 {index+1}: {mask_key(final_api_key)} 차단 → 다른 키로 전환...")
                        break  # 내부 retry 루프 탈출 → 외부 key_attempt 루프로
                    if attempt < max_retries - 1:
                        is_safety = (
                            "safety" in error_msg.lower() or "blocked" in error_msg.lower()
                            or "SAFETY" in error_msg
                            or "이미지가 없습니다" in error_msg
                        )
                        if is_safety:
                            enhanced_prompt = (
                                "A safe, beautiful abstract cinematic visualization, "
                                "National Geographic documentary style, atmospheric lighting, "
                                "bright and uplifting, vertical composition, NO TEXT, NO LETTERS."
                            )
                            print(f"  [{model_label} 경고] 컷 {index+1} 안전 정책 위반. 대체 프롬프트로 재시도 ({attempt+1}/{max_retries})")
                        else:
                            print(f"  [{model_label} 경고] 컷 {index+1} 실패. 3초 후 재시도 ({attempt+1}/{max_retries}) | {e}")
                        time.sleep(3)
                    else:
                        raise RuntimeError(f"[{model_label} 이미지 생성 최종 실패] index={index}: {e}")
            # break로 나왔으면 (429) → 다음 키로 계속

        # 이 모델의 키 전부 소진 → 다음 모델로 폴백
        if model_idx < len(model_chain) - 1:
            print(f"  [모델 체인] {model_label} 전 키 소진 → {model_chain[model_idx + 1]['label']}로 전환...")

    raise RuntimeError(f"[Imagen] 컷 {index+1}: 모든 모델 체인 및 키 소진")


def _generate_imagen(api_key, prompt, model_name):
    """google-genai SDK로 Imagen 이미지를 생성합니다."""
    from google import genai
    from google.genai import types

    safety_level = os.getenv("IMAGEN_SAFETY_FILTER", "BLOCK_LOW_AND_ABOVE")
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

    raise ValueError("Imagen API 이미지 데이터를 추출할 수 없습니다 (image_bytes 없음).")
