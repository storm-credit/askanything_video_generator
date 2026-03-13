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
    429 에러 시 다른 키로 자동 전환하여 재시도합니다 (최대 3회).
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
    model_name = os.getenv("VEO_MODEL", DEFAULT_MODEL)

    tried_keys: set[str] = set()
    current_key = api_key

    for attempt in range(MAX_KEY_RETRIES):
        # 키 선택 (이전에 실패한 키 제외)
        if attempt == 0:
            final_key = current_key or get_google_key(service="veo3")
        else:
            final_key = get_google_key(service="veo3", exclude=tried_keys)

        if not final_key:
            print("[Veo 3 오류] 사용 가능한 API 키가 없습니다.")
            return None

        if final_key in tried_keys:
            # 새 키를 못 찾음 (전부 소진)
            print(f"[Veo 3] 컷 {index+1}: 사용 가능한 키가 더 이상 없습니다. ({len(tried_keys)}개 소진)")
            return None

        tried_keys.add(final_key)
        client = genai.Client(api_key=final_key)

        if attempt > 0:
            print(f"-> [Veo 3] 컷 {index+1} 다른 키로 재시도 중... (시도 {attempt+1}/{MAX_KEY_RETRIES}, 키: {mask_key(final_key)})")
        else:
            print(f"-> [Veo 3] 컷 {index+1} 이미지-투-비디오 렌더링 요청 중... ({model_name})")

        try:
            operation = client.models.generate_videos(
                model=model_name,
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
                mark_key_exhausted(final_key, "veo3")
                print(f"[Veo 3 쿼터 초과] 컷 {index+1}: 키 차단됨 → 다른 키로 전환 시도...")
                continue  # 다음 키로 재시도
            else:
                print(f"[Veo 3 오류] 컷 {index+1} 요청 실패: {e}")
                return None

        # 폴링 대기
        print(f"-> [Veo 3] 컷 {index+1} 클라우드 렌더링 대기 중 (약 1~3분 소요)...")
        start = time.time()

        try:
            while not operation.done:
                time.sleep(POLL_INTERVAL)
                operation = client.operations.get(operation)
                elapsed = time.time() - start
                if elapsed > MAX_WAIT:
                    print(f"[Veo 3 타임아웃] 컷 {index+1}: {MAX_WAIT}초 초과")
                    return None

            result = operation.result
            if not hasattr(result, "generated_videos") or not result.generated_videos:
                print(f"[Veo 3 오류] 컷 {index+1}: 비디오가 생성되지 않았습니다.")
                return None

            video_obj = result.generated_videos[0]
        except Exception as e:
            err_str = str(e)
            if is_key_rotation_error(err_str):
                mark_key_exhausted(final_key, "veo3")
                continue
            print(f"[Veo 3 오류] 컷 {index+1} 폴링 실패: {e}")
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
                    record_key_usage(final_key, "veo3")
                    elapsed = time.time() - start
                    print(f"OK [Veo 3] 컷 {index+1} 렌더링 완료! ({elapsed:.0f}초)")
                    return final_path
                elif hasattr(vid, "uri") and vid.uri:
                    print(f"-> [Veo 3] 컷 {index+1} 비디오 다운로드 중...")
                    resp = requests.get(vid.uri, stream=True, timeout=60)
                    resp.raise_for_status()
                    with open(final_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            f.write(chunk)
                    record_key_usage(final_key, "veo3")
                    elapsed = time.time() - start
                    print(f"OK [Veo 3] 컷 {index+1} 렌더링 완료! ({elapsed:.0f}초)")
                    return final_path

            print(f"[Veo 3 오류] 컷 {index+1}: 비디오 데이터를 찾을 수 없습니다.")
            return None
        except Exception as e:
            print(f"[Veo 3 다운로드 오류] 컷 {index+1}: {e}")
            return None

    print(f"[Veo 3] 컷 {index+1}: {MAX_KEY_RETRIES}개 키 모두 쿼터 초과. 비디오 생성 불가.")
    return None
