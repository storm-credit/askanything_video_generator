"""
Google Veo 3 비디오 생성 모듈
google-genai SDK를 사용하여 이미지 → 비디오 변환을 수행합니다.
429 에러 시 다른 키로 자동 재시도 (최대 3회).
"""

import os
import time
import requests

from modules.utils.keys import record_key_usage, mark_key_exhausted, get_google_key, mask_key
from modules.utils.constants import is_key_rotation_error
from modules.utils.models import get_model_chain, get_service_tag

# Veo 모델 옵션 (환경변수로 오버라이드 가능)
DEFAULT_MODEL = "veo-3.0-generate-001"
POLL_INTERVAL = 10  # 초
MAX_WAIT = 300  # 5분
MAX_KEY_RETRIES = 10  # 키 전환 최대 횟수 (무료 키 다수 → 유료 키 도달까지)


def generate_video_veo(
    image_path: str,
    prompt: str,
    index: int,
    topic_folder: str,
    api_key: str = None,
) -> str | None:
    """
    Google Veo 3로 이미지를 비디오로 변환합니다.
    429 에러 시 다른 키로 자동 전환, 전 키 소진 시 Fast 모델로 자동 폴백.
    """
    if not os.path.exists(image_path):
        print(f"[Veo 3 오류] 이미지 파일을 찾을 수 없습니다: {image_path}")
        return None

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("[Veo 3 오류] google-genai 패키지가 없습니다. (pip install google-genai)")
        return None

    # 이미지 로드 (한 번만)
    with open(image_path, "rb") as f:
        img_bytes = f.read()
    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    mime_type = mime_map.get(ext, "image/png")

    # 모델 체인: 환경변수 오버라이드 시 단일 모델, 아니면 Standard → Fast
    override_model = os.getenv("VEO_MODEL")
    if override_model:
        model_chain = [{"id": override_model, "tag": "override", "label": override_model}]
    else:
        model_chain = get_model_chain("veo3")
        if not model_chain:
            model_chain = [{"id": DEFAULT_MODEL, "tag": "standard", "label": "Veo 3"}]

    for model_idx, model in enumerate(model_chain):
        model_id = model["id"]
        model_label = model["label"]
        service_tag = get_service_tag("veo3", model_id)

        tried_keys: set[str] = set()
        current_key = api_key

        for attempt in range(MAX_KEY_RETRIES):
            # 키 선택 (이전에 실패한 키 제외)
            if attempt == 0:
                final_key = current_key or get_google_key(service=service_tag)
            else:
                final_key = get_google_key(service=service_tag, exclude=tried_keys)

            if not final_key:
                break  # 이 모델에 사용 가능한 키 없음 → 다음 모델로

            if final_key in tried_keys:
                break  # 새 키 없음 → 다음 모델로

            tried_keys.add(final_key)
            client = genai.Client(api_key=final_key)

            if attempt > 0:
                print(f"-> [{model_label}] 컷 {index+1} 다른 키로 재시도 중... (시도 {attempt+1}/{MAX_KEY_RETRIES}, 키: {mask_key(final_key)})")
            elif model_idx == 0:
                print(f"-> [{model_label}] 컷 {index+1} 이미지-투-비디오 렌더링 요청 중... ({model_id})")
            else:
                print(f"-> [{model_label}] 컷 {index+1} 폴백 렌더링 요청 중... ({model_id})")

            try:
                operation = client.models.generate_videos(
                    model=model_id,
                    prompt=f"Cinematic movement, smooth camera motion, 4K quality. {prompt}",
                    image=types.Image(image_bytes=img_bytes, mime_type=mime_type),
                    config=types.GenerateVideosConfig(
                        numberOfVideos=1,
                        durationSeconds=8,
                        aspectRatio="9:16",
                    ),
                )
            except Exception as e:
                err_str = str(e)
                if is_key_rotation_error(err_str):
                    mark_key_exhausted(final_key, service_tag)
                    print(f"[{model_label} 쿼터 초과] 컷 {index+1}: 키 차단됨 → 다른 키로 전환 시도...")
                    continue  # 다음 키로 재시도
                else:
                    print(f"[{model_label} 오류] 컷 {index+1} 요청 실패: {e}")
                    return None

            # 폴링 대기
            print(f"-> [{model_label}] 컷 {index+1} 클라우드 렌더링 대기 중 (약 1~3분 소요)...")
            start = time.time()

            try:
                while not operation.done:
                    time.sleep(POLL_INTERVAL)
                    operation = client.operations.get(operation)
                    elapsed = time.time() - start
                    if elapsed > MAX_WAIT:
                        print(f"[{model_label} 타임아웃] 컷 {index+1}: {MAX_WAIT}초 초과")
                        return None

                result = operation.result
                if not hasattr(result, "generated_videos") or not result.generated_videos:
                    print(f"[{model_label} 오류] 컷 {index+1}: 비디오가 생성되지 않았습니다.")
                    return None

                video_obj = result.generated_videos[0]
            except Exception as e:
                err_str = str(e)
                if is_key_rotation_error(err_str):
                    mark_key_exhausted(final_key, service_tag)
                    continue
                print(f"[{model_label} 오류] 컷 {index+1} 폴링 실패: {e}")
                return None

            # 비디오 다운로드
            output_dir = os.path.join("assets", topic_folder, "video_clips")
            os.makedirs(output_dir, exist_ok=True)
            final_path = os.path.join(output_dir, f"veo3_cut_{index:02d}.mp4")

            try:
                if hasattr(video_obj, "video") and video_obj.video:
                    vid = video_obj.video
                    if hasattr(vid, "video_bytes") and vid.video_bytes:
                        with open(final_path, "wb") as f:
                            f.write(vid.video_bytes)
                        record_key_usage(final_key, service_tag)
                        elapsed = time.time() - start
                        print(f"OK [{model_label}] 컷 {index+1} 렌더링 완료! ({elapsed:.0f}초)")
                        return final_path
                    elif hasattr(vid, "uri") and vid.uri:
                        print(f"-> [{model_label}] 컷 {index+1} 비디오 다운로드 중...")
                        resp = requests.get(vid.uri, stream=True, timeout=60)
                        resp.raise_for_status()
                        with open(final_path, "wb") as f:
                            for chunk in resp.iter_content(chunk_size=8192):
                                f.write(chunk)
                        record_key_usage(final_key, service_tag)
                        elapsed = time.time() - start
                        print(f"OK [{model_label}] 컷 {index+1} 렌더링 완료! ({elapsed:.0f}초)")
                        return final_path

                print(f"[{model_label} 오류] 컷 {index+1}: 비디오 데이터를 찾을 수 없습니다.")
                return None
            except Exception as e:
                print(f"[{model_label} 다운로드 오류] 컷 {index+1}: {e}")
                return None

        # 이 모델의 키 전부 소진 → 다음 모델로 폴백
        if model_idx < len(model_chain) - 1:
            print(f"  [모델 체인] {model_label} 전 키 소진 → {model_chain[model_idx + 1]['label']}로 전환...")

    print(f"[Veo] 컷 {index+1}: 모든 모델 체인 및 키 소진. 비디오 생성 불가.")
    return None
