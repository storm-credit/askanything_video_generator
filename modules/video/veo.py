"""
Google Veo 3 비디오 생성 모듈
google-genai SDK를 사용하여 이미지 → 비디오 변환을 수행합니다.
Higgsfield 없이 Google API 키 하나로 동작합니다.
"""

import os
import time

from modules.utils.keys import record_key_usage, mark_key_exhausted

# Veo 모델 옵션 (환경변수로 오버라이드 가능)
DEFAULT_MODEL = "veo-3.0-generate-001"
POLL_INTERVAL = 10  # 초
MAX_WAIT = 300  # 5분

# 사전 체크: Veo가 사용 가능한지 빠르게 확인
def check_veo_available(api_key: str = None) -> tuple[bool, str]:
    """Veo 모델 사용 가능 여부를 확인합니다. (ok, reason) 반환."""
    final_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not final_key:
        return False, "GEMINI_API_KEY 또는 GOOGLE_API_KEY가 필요합니다"
    try:
        from google import genai
        client = genai.Client(api_key=final_key)
        models = [m.name for m in client.models.list()]
        veo_models = [m for m in models if "veo" in m.lower()]
        if not veo_models:
            return False, "이 API 키로는 Veo 모델을 사용할 수 없습니다"
        return True, f"{len(veo_models)}개 Veo 모델 사용 가능"
    except Exception as e:
        return False, f"Veo 사용 불가: {e}"


def generate_video_veo(
    image_path: str,
    prompt: str,
    index: int,
    topic_folder: str,
    api_key: str = None,
) -> str | None:
    """
    Google Veo 3로 이미지를 비디오로 변환합니다.
    실패 시 None 반환 (호출자가 정지 이미지로 폴백).
    """
    final_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not final_key:
        print("[Veo 3 오류] GEMINI_API_KEY 또는 GOOGLE_API_KEY가 없습니다.")
        return None

    if not os.path.exists(image_path):
        print(f"[Veo 3 오류] 이미지 파일을 찾을 수 없습니다: {image_path}")
        return None

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        print("[Veo 3 오류] google-genai 패키지가 없습니다. (pip install google-genai)")
        return None

    model_name = os.getenv("VEO_MODEL", DEFAULT_MODEL)
    client = genai.Client(api_key=final_key)

    # 이미지 로드
    with open(image_path, "rb") as f:
        img_bytes = f.read()

    # MIME 타입 결정
    ext = os.path.splitext(image_path)[1].lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    mime_type = mime_map.get(ext, "image/png")

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
        if "429" in err_str or "quota" in err_str.lower() or "rate" in err_str.lower() or "RESOURCE_EXHAUSTED" in err_str:
            mark_key_exhausted(final_key, "veo3")
            print(f"[Veo 3 쿼터 초과] 컷 {index+1}: 일일 생성 한도 도달. 이 키는 24시간 후 자동 해제됩니다.")
        else:
            print(f"[Veo 3 오류] 컷 {index+1} 요청 실패: {e}")
        return None

    # 비동기 폴링 대기
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
        print(f"[Veo 3 오류] 컷 {index+1} 폴링 실패: {e}")
        return None

    # 비디오 다운로드
    output_dir = os.path.join("assets", topic_folder, "video_clips")
    os.makedirs(output_dir, exist_ok=True)
    final_path = os.path.join(output_dir, f"veo3_cut_{index:02d}.mp4")

    try:
        # video_bytes가 있으면 직접 저장
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
                # URI에서 다운로드
                import requests
                print(f"-> [Veo 3] 컷 {index+1} 비디오 다운로드 중...")
                resp = requests.get(vid.uri, timeout=60)
                with open(final_path, "wb") as f:
                    f.write(resp.content)
                record_key_usage(final_key, "veo3")
                elapsed = time.time() - start
                print(f"OK [Veo 3] 컷 {index+1} 렌더링 완료! ({elapsed:.0f}초)")
                return final_path

        print(f"[Veo 3 오류] 컷 {index+1}: 비디오 데이터를 찾을 수 없습니다.")
        return None
    except Exception as e:
        print(f"[Veo 3 다운로드 오류] 컷 {index+1}: {e}")
        return None
