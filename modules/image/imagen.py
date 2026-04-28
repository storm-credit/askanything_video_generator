import os
import shutil
import tempfile
import time
from PIL import Image, ImageOps
import io

from modules.utils.keys import record_key_usage, mark_key_exhausted, get_google_key, mask_key, check_rpm_available, record_rpm_usage, exponential_backoff_wait
from modules.utils.constants import MASTER_STYLE, is_key_rotation_error
from modules.utils.cache import get_cached_image, save_to_cache
from modules.utils.models import get_model_chain, get_service_tag
from modules.utils.safety import is_safety_error, get_safety_fallback_prompt
from modules.utils.project_quota import quota_manager

MAX_KEY_RETRIES = 10  # 키 전환 최대 횟수
MAX_PROJECT_RETRIES = 5  # 프로젝트 전환 최대 횟수



def generate_image_with_quota(prompt: str, index: int, topic_folder: str = "default_topic",
                              model_override: str | None = None, topic: str = "") -> str:
    """QuotaManager 기반 이미지 생성 — 프로젝트 단위 관리.

    기존 generate_image_imagen()을 감싸서 프로젝트 선택 → 생성 → 결과 보고.
    다른 모듈에서 이걸 import해서 쓰면 됨.
    """
    last_error = None
    for attempt in range(MAX_PROJECT_RETRIES):
        try:
            project_name, api_key, key_alias = quota_manager.acquire()
            print(f"[QuotaManager] 컷 {index+1} project={project_name} key={key_alias}")

            result = generate_image_imagen(
                prompt, index, topic_folder,
                api_key=api_key, model_override=model_override, topic=topic,
            )
            quota_manager.mark_success(project_name)
            return result

        except Exception as e:
            last_error = e
            error_text = str(e).lower()
            print(f"[QuotaManager] 컷 {index+1} 실패 project={project_name} error={error_text[:150]}")

            if "429" in error_text or "resource_exhausted" in error_text:
                quota_manager.mark_rate_limited(project_name=project_name, reason=error_text, mode="auto")
            elif "paid plan" in error_text or "upgrade your account" in error_text:
                quota_manager.mark_paid_only(project_name)
            else:
                quota_manager.mark_error(project_name=project_name, reason=error_text)
                raise  # 429/유료 외 에러는 재시도 안 함

    raise last_error or RuntimeError(f"[QuotaManager] 컷 {index+1}: 모든 프로젝트 소진")


def generate_image_imagen(prompt: str, index: int, topic_folder: str = "default_topic", api_key: str | None = None, model_override: str | None = None, gemini_api_keys: str | None = None, topic: str = "") -> str:
    """
    Google Imagen 4 API로 이미지를 생성합니다.
    429 에러 시 다른 키로 자동 전환, 전 키 소진 시 Fast 모델로 자동 폴백.
    """
    if not prompt or not prompt.strip():
        raise ValueError(f"[Imagen 이미지 오류] 프롬프트가 비어 있습니다 (index={index})")
    is_vertex_backend = os.getenv("GEMINI_BACKEND") == "vertex_ai"

    # ── 캐시 확인 ──
    cache_key_prompt = MASTER_STYLE + prompt
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

    for model_idx, model in enumerate(model_chain):
        model_id = model["id"]
        model_label = model["label"]
        service_tag = get_service_tag("imagen", model_id)

        # 모델 체인 반복마다 프롬프트 초기화 (safety 폴백으로 변경된 프롬프트 리셋)
        enhanced_prompt = MASTER_STYLE + prompt
        safety_retry_count = 0  # safety fallback stage tracker

        tried_keys: set[str] = set()
        current_key = api_key
        key_attempt = 0

        while key_attempt < MAX_KEY_RETRIES:
            # 키 선택 (이전에 429 난 키 제외)
            if is_vertex_backend:
                final_api_key = current_key
            elif key_attempt == 0:
                final_api_key = current_key or get_google_key(service=service_tag, extra_keys=gemini_api_keys)
            else:
                final_api_key = get_google_key(service=service_tag, exclude=tried_keys, extra_keys=gemini_api_keys)

            if not is_vertex_backend and not final_api_key:
                break  # 이 모델에 사용 가능한 키 없음 → 다음 모델로

            if final_api_key:
                tried_keys.add(final_api_key)

            # RPM 체크 — 한도 초과 시 잠시 대기
            if final_api_key and not is_vertex_backend and not check_rpm_available(final_api_key, service_tag):
                wait = exponential_backoff_wait(key_attempt, base=1.5, max_wait=10)
                print(f"  [{model_label}] 컷 {index+1} RPM 한도 근접, {wait:.1f}초 대기...")
                time.sleep(wait)

            if key_attempt > 0 and final_api_key:
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
                fd, tmp_img = tempfile.mkstemp(dir=image_dir, suffix=".tmp")
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

                if final_api_key and not is_vertex_backend:
                    record_key_usage(final_api_key, service_tag)
                    record_rpm_usage(final_api_key, service_tag)
                save_to_cache(cache_key_prompt, filename)
                print(f"OK [아트 디렉터] 컷 {index+1} {model_label} 렌더링 완료!")
                return filename

            except Exception as e:
                error_msg = str(e)
                # 429/503/유료전용 → 키 차단 후 다른 키로 전환
                if is_key_rotation_error(error_msg):
                    if final_api_key and not is_vertex_backend:
                        mark_key_exhausted(final_api_key, service_tag)
                    elif is_vertex_backend:
                        try:
                            from modules.utils.gemini_client import get_current_sa_key, mark_sa_key_blocked
                            current_sa = get_current_sa_key()
                            if current_sa:
                                mark_sa_key_blocked(current_sa, block_seconds=60)
                        except Exception as sa_err:
                            print(f"  [{model_label} Vertex SA 차단 경고] {sa_err}")
                    # 지수 백오프: 다음 키 시도 전 잠시 대기
                    backoff = exponential_backoff_wait(key_attempt, base=2.0, max_wait=30)
                    if final_api_key and not is_vertex_backend:
                        print(f"  [{model_label} 키 전환] 컷 {index+1}: {mask_key(final_api_key)} 차단 → {backoff:.1f}초 대기 후 다른 키로...")
                    else:
                        print(f"  [{model_label} Vertex 재시도] 컷 {index+1}: {backoff:.1f}초 대기 후 다른 SA로...")
                    time.sleep(backoff)
                    key_attempt += 1
                    continue
                if is_safety_error(error_msg) and safety_retry_count < 3:
                    enhanced_prompt = MASTER_STYLE + get_safety_fallback_prompt(prompt, safety_retry_count, topic=topic)
                    safety_retry_count += 1
                    if final_api_key:
                        tried_keys.discard(final_api_key)  # safety 재시도는 같은 키로
                    print(f"  [{model_label} 경고] 컷 {index+1} 안전 정책 위반. 대체 프롬프트로 재시도... ({safety_retry_count}/3)")
                    continue  # key_attempt 증가 안 함 — 키 로테이션 예산 소모 방지
                print(f"  [{model_label} 실패] 컷 {index+1}: {e}")
                break  # 이 모델 포기 → 다음 모델로 폴백

        # 이 모델의 키 전부 소진 → 다음 모델로 폴백
        if model_idx < len(model_chain) - 1:
            print(f"  [모델 체인] {model_label} 전 키 소진 → {model_chain[model_idx + 1]['label']}로 전환...")

    # Imagen 전체 소진 → Nano Banana 자동 폴백
    print(f"  [Imagen → Nano Banana 폴백] 컷 {index+1}: Imagen 모든 모델/키 소진, Nano Banana로 전환...")
    try:
        return generate_image_nano_banana(prompt, index, topic_folder, api_key=None, gemini_api_keys=gemini_api_keys, topic=topic)
    except Exception as nb_err:
        raise RuntimeError(f"[Imagen+NanoBanana] 컷 {index+1}: 모든 이미지 엔진 및 키 소진") from nb_err


# ── Nano Banana (Gemini 네이티브 이미지 생성) — Imagen과 별도 쿼터 ──
NANO_BANANA_MODELS = [
    "gemini-2.5-flash-image",            # 가장 빠름
    "gemini-2.0-flash-image-generation", # 무료 폴백
]


def generate_image_nano_banana(prompt: str, index: int, topic_folder: str, api_key: str | None = None, gemini_api_keys: str | None = None, topic: str = "") -> str:
    """Nano Banana (Gemini 네이티브 이미지 생성)로 이미지를 생성합니다. Imagen 폴백용. 키 로테이션 지원."""
    from google.genai import types
    from modules.utils.gemini_client import create_gemini_client

    enhanced_prompt = MASTER_STYLE + prompt
    is_vertex_backend = os.getenv("GEMINI_BACKEND") == "vertex_ai"

    image_dir = os.path.join("assets", topic_folder, "images")
    os.makedirs(image_dir, exist_ok=True)
    filename = os.path.join(image_dir, f"cut_{index:02}.png")

    last_error = None
    for model_name in NANO_BANANA_MODELS:
        tried_keys: set[str] = set()
        service_tag = f"nano_{model_name.split('-')[1]}"

        for key_attempt in range(MAX_KEY_RETRIES):
            # 키 로테이션: 이전 실패 키 제외하고 다음 키 선택
            if is_vertex_backend:
                final_key = api_key
            elif key_attempt == 0:
                final_key = api_key or get_google_key(service=service_tag, extra_keys=gemini_api_keys)
            else:
                final_key = get_google_key(service=service_tag, exclude=tried_keys, extra_keys=gemini_api_keys)

            if not is_vertex_backend and not final_key:
                print(f"  [Nano Banana] {model_name} 사용 가능한 키 없음 → 다음 모델로")
                break

            if final_key:
                tried_keys.add(final_key)

            try:
                if key_attempt == 0:
                    print(f"  [Nano Banana] 컷 {index+1} {model_name}로 생성 중...")
                elif final_key:
                    print(f"  [Nano Banana] 컷 {index+1} 다른 키로 재시도 ({key_attempt+1}/{MAX_KEY_RETRIES}, 키: {mask_key(final_key)})")
                else:
                    print(f"  [Nano Banana] 컷 {index+1} 다른 SA로 재시도 ({key_attempt+1}/{MAX_KEY_RETRIES})")

                client = create_gemini_client(api_key=final_key)
                response = client.models.generate_content(
                    model=model_name,
                    contents=enhanced_prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE"],
                        image_config=types.ImageConfig(
                            aspect_ratio="9:16",
                        ),
                    ),
                )

                # 이미지 파트 추출
                image_bytes = None
                for part in response.parts:
                    if part.inline_data is not None:
                        image_bytes = part.inline_data.data
                        break

                if not image_bytes:
                    raise ValueError(f"Nano Banana 응답에 이미지가 없습니다 ({model_name})")

                # 저장
                image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                target_size = (1080, 1920)
                fitted = ImageOps.fit(image, target_size, method=Image.LANCZOS, centering=(0.5, 0.5))

                fd, tmp = tempfile.mkstemp(dir=image_dir, suffix=".tmp")
                os.close(fd)
                try:
                    fitted.save(tmp, format="PNG")
                    os.replace(tmp, filename)
                except Exception:
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
                    raise

                save_to_cache(enhanced_prompt, filename)
                if final_key and not is_vertex_backend:
                    print(f"  [Nano Banana] 컷 {index+1} 생성 완료 ({model_name}, 키: {mask_key(final_key)})")
                else:
                    print(f"  [Nano Banana] 컷 {index+1} 생성 완료 ({model_name}, Vertex SA)")
                return filename

            except Exception as e:
                error_msg = str(e)
                last_error = e
                if is_key_rotation_error(error_msg):
                    if final_key and not is_vertex_backend:
                        mark_key_exhausted(final_key, service_tag)
                        print(f"  [Nano Banana 키 전환] 컷 {index+1}: {mask_key(final_key)} 차단 → 다른 키로")
                    else:
                        try:
                            from modules.utils.gemini_client import get_current_sa_key, mark_sa_key_blocked
                            current_sa = get_current_sa_key()
                            if current_sa:
                                mark_sa_key_blocked(current_sa, block_seconds=60)
                        except Exception as sa_err:
                            print(f"  [Nano Banana Vertex SA 차단 경고] {sa_err}")
                        print(f"  [Nano Banana Vertex 재시도] 컷 {index+1}: 다른 SA로 전환")
                    continue
                print(f"  [Nano Banana] {model_name} 실패: {e}")
                break  # 이 모델 포기 → 다음 모델로

    raise RuntimeError(f"[Nano Banana] 컷 {index+1}: 모든 모델·키 소진 — {last_error}")


def _generate_imagen(api_key: str, prompt: str, model_name: str) -> bytes:
    """google-genai SDK로 Imagen 이미지를 생성합니다."""
    from google.genai import types
    from modules.utils.gemini_client import create_gemini_client

    safety_level = os.getenv("IMAGEN_SAFETY_FILTER", "BLOCK_LOW_AND_ABOVE")
    client = create_gemini_client(api_key=api_key)
    response = client.models.generate_images(
        model=model_name,
        prompt=prompt,
        config=types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="9:16",
            safety_filter_level=safety_level,
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
