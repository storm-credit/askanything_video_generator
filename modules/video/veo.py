"""
Google Veo 3 비디오 생성 모듈
google-genai SDK를 사용하여 이미지 → 비디오 변환을 수행합니다.
429 에러 시 다른 키로 자동 재시도 (최대 3회).
"""

import os
import time
import requests

from modules.utils.keys import record_key_usage, mark_key_exhausted, get_google_key, mask_key
from modules.utils.constants import is_key_rotation_error, get_motion_style
from modules.utils.models import get_model_chain, get_service_tag

# Veo 모델 옵션 (환경변수로 오버라이드 가능)
DEFAULT_MODEL = "veo-3.0-generate-001"
POLL_INTERVAL_INITIAL = 5   # 초 (시작)
POLL_INTERVAL_MID = 10      # 1분 후
POLL_INTERVAL_LATE = 15     # 2분 후
MAX_WAIT = 300  # 5분
MAX_KEY_RETRIES = 10  # 키 전환 최대 횟수 (무료 키 다수 → 유료 키 도달까지)


def generate_video_veo(
    image_path: str,
    prompt: str,
    index: int,
    topic_folder: str,
    api_key: str = None,
    description: str = "",
    model_override: str | None = None,
    gemini_api_keys: str | None = None,
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

    # 모델 체인: 파라미터 오버라이드 → 환경변수 → 기본 모델 체인
    override_model = model_override or os.getenv("VEO_MODEL")
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
                final_key = current_key or get_google_key(service=service_tag, extra_keys=gemini_api_keys)
            else:
                final_key = get_google_key(service=service_tag, exclude=tried_keys, extra_keys=gemini_api_keys)

            if not final_key:
                break  # 이 모델에 사용 가능한 키 없음 → 다음 모델로

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
                    prompt=f"{get_motion_style(prompt, description)}, 4K cinematic quality. {prompt}",
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
                    break  # 이 모델 포기 → 다음 모델로 폴백

            # 폴링 대기
            print(f"-> [{model_label}] 컷 {index+1} 클라우드 렌더링 대기 중 (약 1~3분 소요)...")
            start = time.time()

            try:
                while not operation.done:
                    elapsed = time.time() - start
                    poll_interval = POLL_INTERVAL_INITIAL if elapsed < 60 else (POLL_INTERVAL_MID if elapsed < 120 else POLL_INTERVAL_LATE)
                    time.sleep(poll_interval)
                    operation = client.operations.get(operation)
                    elapsed = time.time() - start
                    if elapsed > MAX_WAIT:
                        print(f"[{model_label} 타임아웃] 컷 {index+1}: {MAX_WAIT}초 초과, 다른 키로 재시도...")
                        break  # return None → break: 다음 키/모델로 폴백

                if not operation.done:
                    continue  # 타임아웃으로 break됨 → 다음 키 시도

                result = operation.result
                if not hasattr(result, "generated_videos") or not result.generated_videos:
                    print(f"[{model_label} 오류] 컷 {index+1}: 비디오가 생성되지 않았습니다. 다른 키로 재시도...")
                    continue  # 다음 키로 재시도

                video_obj = result.generated_videos[0]
            except Exception as e:
                err_str = str(e)
                if is_key_rotation_error(err_str):
                    mark_key_exhausted(final_key, service_tag)
                    continue
                print(f"[{model_label} 오류] 컷 {index+1} 폴링 실패: {e}")
                break  # 이 모델 포기 → 다음 모델로 폴백

            # 비디오 다운로드
            output_dir = os.path.join("assets", topic_folder, "video_clips")
            os.makedirs(output_dir, exist_ok=True)
            final_path = os.path.join(output_dir, f"veo3_cut_{index:02d}.mp4")

            try:
                if hasattr(video_obj, "video") and video_obj.video:
                    vid = video_obj.video
                    if hasattr(vid, "video_bytes") and vid.video_bytes:
                        import tempfile as _tmpfile2
                        fd, tmp_vb = _tmpfile2.mkstemp(dir=output_dir, suffix=".tmp")
                        os.close(fd)
                        try:
                            with open(tmp_vb, "wb") as f:
                                f.write(vid.video_bytes)
                            os.replace(tmp_vb, final_path)
                        except Exception:
                            try:
                                os.remove(tmp_vb)
                            except OSError:
                                pass
                            raise
                        record_key_usage(final_key, service_tag)
                        elapsed = time.time() - start
                        print(f"OK [{model_label}] 컷 {index+1} 렌더링 완료! ({elapsed:.0f}초)")
                        return final_path
                    elif hasattr(vid, "uri") and vid.uri:
                        import tempfile as _tmpfile
                        print(f"-> [{model_label}] 컷 {index+1} 비디오 다운로드 중...")
                        resp = requests.get(vid.uri, stream=True, timeout=60)
                        resp.raise_for_status()
                        fd, tmp_dl = _tmpfile.mkstemp(dir=output_dir, suffix=".tmp")
                        os.close(fd)
                        try:
                            with open(tmp_dl, "wb") as f:
                                for chunk in resp.iter_content(chunk_size=8192):
                                    f.write(chunk)
                            os.replace(tmp_dl, final_path)
                        except Exception:
                            try:
                                os.remove(tmp_dl)
                            except OSError:
                                pass
                            raise
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
