import os
import shutil
import time
from PIL import Image, ImageOps
import io

from modules.utils.keys import record_key_usage, mark_key_exhausted, get_google_key, mask_key
from modules.utils.constants import is_key_rotation_error
from modules.utils.cache import get_cached_image, save_to_cache
from modules.utils.models import get_model_chain, get_service_tag
from modules.utils.safety import is_safety_error, get_safety_fallback_prompt

MAX_KEY_RETRIES = 10  # 키 전환 최대 횟수 (무료 키 다수 → 유료 키 도달까지)


def generate_image_imagen(prompt: str, index: int, topic_folder: str = "default_topic", api_key: str | None = None, model_override: str | None = None, gemini_api_keys: str | None = None, channel: str | None = None) -> str:
    """
    Google Imagen 4 API로 이미지를 생성합니다.
    429 에러 시 다른 키로 자동 전환, 전 키 소진 시 Fast 모델로 자동 폴백.
    channel 지정 시 채널별 MASTER_STYLE 적용 (YouTube 중복 감지 방지).
    """
    if not prompt or not prompt.strip():
        raise ValueError(f"[Imagen 이미지 오류] 프롬프트가 비어 있습니다 (index={index})")

    # 채널별 MASTER_STYLE 결정
    from modules.utils.channel_config import get_master_style
    active_master_style = get_master_style(channel)

    # ── 캐시 확인 (모델명 포함 — Standard/Fast 혼동 방지) ──
    _cache_model = model_override or "default"
    cache_key_prompt = f"{_cache_model}:{active_master_style}{prompt}"
    cached = get_cached_image(cache_key_prompt)
    if cached:
        image_dir = f"assets/{topic_folder}/images"
        os.makedirs(image_dir, exist_ok=True)
        filename = os.path.join(image_dir, f"cut_{index:02}.png")
        shutil.copy2(cached, filename)
        print(f"[이미지 캐시] 히트 — 재생성 스킵 (컷 {index+1})")
        return filename

    # 모델 체인: 파라미터 오버라이드 → 환경변수 → 기본 모델 체인
    override_model = model_override or os.getenv("IMAGEN_MODEL")
    if override_model:
        model_chain = [{"id": override_model, "tag": "override", "label": override_model}]
    else:
        model_chain = get_model_chain("imagen")
        if not model_chain:
            model_chain = [{"id": "imagen-4.0-generate-001", "tag": "standard", "label": "Imagen 4"}]

    global_safety_retries = 0  # 전체 모델 체인 안전 리트라이 상한
    MAX_GLOBAL_SAFETY = 4     # 모든 모델 합산 최대 안전 리트라이 횟수

    for model_idx, model in enumerate(model_chain):
        model_id = model["id"]
        model_label = model["label"]
        service_tag = get_service_tag("imagen", model_id)

        # 모델 체인 반복마다 프롬프트 초기화 (safety 폴백으로 변경된 프롬프트 리셋)
        enhanced_prompt = active_master_style + prompt
        safety_retry_count = 0  # safety fallback stage tracker

        tried_keys: set[str] = set()
        current_key = api_key
        key_attempt = 0

        while key_attempt < MAX_KEY_RETRIES:
            # 키 선택 (이전에 429 난 키 제외)
            if key_attempt == 0:
                final_api_key = current_key or get_google_key(service=service_tag, extra_keys=gemini_api_keys)
            else:
                final_api_key = get_google_key(service=service_tag, exclude=tried_keys, extra_keys=gemini_api_keys)

            if not final_api_key:
                break  # 이 모델에 사용 가능한 키 없음 → 다음 모델로

            tried_keys.add(final_api_key)

            if key_attempt > 0:
                print(f"  [{model_label}] 컷 {index+1} 다른 키로 재시도 (시도 {key_attempt+1}/{MAX_KEY_RETRIES}, 키: {mask_key(final_api_key)})")

            if key_attempt == 0 and model_idx == 0:
                print(f"-> [아트 디렉터] 컷 {index+1} {model_label} 렌더링 중...")
            elif key_attempt == 0:
                print(f"-> [아트 디렉터] 컷 {index+1} {model_label}로 폴백 렌더링 중...")

            try:
                image_bytes = _generate_imagen(final_api_key, enhanced_prompt, model_id)

                if not image_bytes:
                    raise ValueError("이미지 생성 결과가 비어 있습니다.")

                image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                target_size = (1080, 1920)
                fitted_image = ImageOps.fit(image, target_size, method=Image.LANCZOS, centering=(0.5, 0.5))

                image_dir = f"assets/{topic_folder}/images"
                os.makedirs(image_dir, exist_ok=True)
                filename = os.path.join(image_dir, f"cut_{index:02}.png")
                import tempfile as _tmpfile
                fd, tmp_img = _tmpfile.mkstemp(dir=image_dir, suffix=".tmp")
                os.close(fd)
                try:
                    fitted_image.save(tmp_img, format="PNG")
                    os.replace(tmp_img, filename)
                except Exception:
                    try:
                        os.remove(tmp_img)
                    except OSError:
                        pass
                    raise

                record_key_usage(final_api_key, service_tag)
                save_to_cache(cache_key_prompt, filename)
                print(f"OK [아트 디렉터] 컷 {index+1} {model_label} 렌더링 완료!")
                return filename

            except Exception as e:
                error_msg = str(e)
                # 429/503/유료전용 → 키 차단 후 다른 키로 전환
                if is_key_rotation_error(error_msg):
                    mark_key_exhausted(final_api_key, service_tag)
                    print(f"  [{model_label} 키 전환] 컷 {index+1}: {mask_key(final_api_key)} 차단 → 다른 키로 전환...")
                    key_attempt += 1  # 키 전환만 카운터 증가
                    continue
                if is_safety_error(error_msg) and safety_retry_count < 3 and global_safety_retries < MAX_GLOBAL_SAFETY:
                    enhanced_prompt = active_master_style + get_safety_fallback_prompt(prompt, safety_retry_count)
                    safety_retry_count += 1
                    global_safety_retries += 1
                    tried_keys.discard(final_api_key)  # safety 재시도는 같은 키로
                    print(f"  [{model_label} 경고] 컷 {index+1} 안전 정책 위반. 대체 프롬프트로 재시도... ({safety_retry_count}/3)")
                    continue  # key_attempt 증가 안 함 — 키 로테이션 예산 소모 방지
                raise RuntimeError(f"[{model_label} 이미지 생성 실패] index={index}: {e}")

        # 이 모델의 키 전부 소진 → 다음 모델로 폴백
        if model_idx < len(model_chain) - 1:
            print(f"  [모델 체인] {model_label} 전 키 소진 → {model_chain[model_idx + 1]['label']}로 전환...")

    raise RuntimeError(f"[Imagen] 컷 {index+1}: 모든 모델 체인 및 키 소진")


def _generate_imagen(api_key: str, prompt: str, model_name: str) -> bytes:
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
            person_generation="ALLOW_ALL",  # 인물 포함 프롬프트 safety 차단 방지
            http_options=types.HttpOptions(timeout=120_000),
        ),
    )

    if not response.generated_images:
        raise ValueError("Imagen API 응답에 이미지가 없습니다.")

    gen_image = response.generated_images[0].image

    # google-genai SDK: image.image_bytes 속성으로 바이트 추출
    if hasattr(gen_image, "image_bytes") and gen_image.image_bytes:
        return gen_image.image_bytes

    raise ValueError("Imagen API 이미지 데이터를 추출할 수 없습니다 (image_bytes 없음).")
