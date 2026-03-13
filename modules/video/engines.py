"""
멀티 비디오 엔진 통합 모듈
- Veo 3: Google genai SDK 직접 연동 (Gemini 키 사용)
- Sora 2: OpenAI API 직접 연동
- Kling: Kling AI 직접 연동 (KLING_ACCESS_KEY/SECRET_KEY)
- Higgsfield: 크레딧 필요 (Kling, Hailuo, Wan 폴백용)
"""

import os
import time
import mimetypes
import requests
import base64

# 지원 엔진 목록 (프론트엔드 드롭다운용)
SUPPORTED_ENGINES = {
    "kling": {"name": "Kling 3.0", "desc": "시네마틱 모션", "provider": "kling_direct"},
    "sora2": {"name": "Sora 2", "desc": "최고 품질 (OpenAI)", "provider": "openai"},
    "veo3": {"name": "Veo 3", "desc": "Google API 직접 연동", "provider": "google"},
    "hailuo": {"name": "Hailuo 2.3", "desc": "가성비 최고 (Higgsfield)", "provider": "higgsfield"},
    "wan": {"name": "Wan 2.5", "desc": "빠른 생성 (Higgsfield)", "provider": "higgsfield"},
    "none": {"name": "비디오 없음", "desc": "정지 이미지만 사용", "provider": "none"},
}

# Sora 2 폴링 설정
SORA_POLL_INTERVAL = 5       # 초 (초기)
SORA_POLL_INTERVAL_SLOW = 10 # 초 (1분 이후)
SORA_MAX_POLLS = 60          # 최대 폴링 횟수
SORA_SLOWDOWN_AT = 12        # 이 횟수 이후 폴링 간격 확대

# 비디오 다운로드 설정
VIDEO_DOWNLOAD_TIMEOUT = 60  # 초
MAX_IMAGE_SIZE_MB = 20       # Base64 인코딩 전 최대 이미지 크기


def get_available_engines() -> list[dict]:
    """프론트엔드에 표시할 사용 가능한 엔진 목록을 반환합니다."""
    available = []
    for key, info in SUPPORTED_ENGINES.items():
        available.append({"id": key, **info})
    return available


def check_engine_available(engine: str, google_key: str = None) -> tuple[bool, str]:
    """엔진 사용 가능 여부를 사전 검증합니다. (ok, reason) 반환."""
    if engine == "none":
        return True, "정지 이미지 모드"

    if engine == "veo3":
        key = google_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            return False, "GEMINI_API_KEY 필요 (Veo 3)"
        return True, "Google API 직접 연동"

    if engine == "sora2":
        key = os.getenv("OPENAI_API_KEY")
        if not key:
            return False, "OPENAI_API_KEY 필요 (Sora 2)"
        return True, "OpenAI API 직접 연동"

    if engine == "kling":
        ak = os.getenv("KLING_ACCESS_KEY")
        sk = os.getenv("KLING_SECRET_KEY")
        if ak and sk:
            return True, "Kling AI 직접 연동"
        # Higgsfield 폴백 체크
        hf_key = os.getenv("HIGGSFIELD_API_KEY")
        if hf_key:
            return True, "Higgsfield 경유 (크레딧 필요)"
        return False, "KLING_ACCESS_KEY + KLING_SECRET_KEY 또는 HIGGSFIELD_API_KEY 필요"

    if engine in ("hailuo", "wan"):
        hf_key = os.getenv("HIGGSFIELD_API_KEY")
        if not hf_key:
            return False, f"HIGGSFIELD_API_KEY 필요 ({SUPPORTED_ENGINES[engine]['name']})"
        return True, "Higgsfield 경유 (크레딧 필요)"

    return False, f"알 수 없는 엔진: {engine}"


def generate_video_from_image(
    image_path: str,
    prompt: str,
    index: int,
    topic_folder: str,
    engine: str = "kling",
    google_api_key: str = None,
) -> str | None:
    """
    선택된 엔진으로 이미지를 비디오로 변환합니다.
    실패 시 None을 반환합니다 (호출자가 정지 이미지로 폴백).
    """
    if engine == "none":
        return None

    if not os.path.exists(image_path):
        print(f"[비디오 엔진 오류] 이미지를 찾을 수 없습니다: {image_path}")
        return None

    # Veo 3: Google genai SDK 직접 사용
    if engine == "veo3":
        from modules.video.veo import generate_video_veo
        return generate_video_veo(image_path, prompt, index, topic_folder, google_api_key)

    # Sora 2: OpenAI API
    if engine == "sora2":
        return _generate_via_openai_sora(image_path, prompt, index, topic_folder)

    # Kling: 직접 API 우선, Higgsfield 폴백
    if engine == "kling":
        ak = os.getenv("KLING_ACCESS_KEY")
        sk = os.getenv("KLING_SECRET_KEY")
        if ak and sk:
            result = _generate_via_kling_direct(image_path, prompt, index, topic_folder)
            if result:
                return result
        # Higgsfield 폴백
        hf_result = _generate_via_higgsfield(image_path, prompt, index, topic_folder, engine)
        if hf_result:
            return hf_result
        print(f"[Kling 오류] 모든 경로 실패 (직접 API: {'설정됨' if ak and sk else '미설정'}, Higgsfield: 실패)")
        return None

    # Hailuo, Wan: Higgsfield 전용
    if engine in ("hailuo", "wan"):
        return _generate_via_higgsfield(image_path, prompt, index, topic_folder, engine)

    print(f"[비디오 엔진 오류] 알 수 없는 엔진: {engine}")
    return None


def _generate_via_higgsfield(
    image_path: str, prompt: str, index: int, topic_folder: str, engine: str
) -> str | None:
    """Higgsfield 통합 API를 통한 비디오 생성"""
    hf_key = os.getenv("HIGGSFIELD_API_KEY")
    hf_account = os.getenv("HIGGSFIELD_ACCOUNT_ID")

    if not hf_key:
        print("[Higgsfield 오류] HIGGSFIELD_API_KEY가 없습니다.")
        return None

    engine_name = SUPPORTED_ENGINES.get(engine, {}).get("name", engine)

    # Higgsfield 모델 매핑
    model_map = {
        "kling": "kling-v2-master",
        "hailuo": "hailuo-02",
        "wan": "wan-2.1",
    }
    model_id = model_map.get(engine)
    if not model_id:
        print(f"[Higgsfield 오류] {engine}에 대한 모델 매핑이 없습니다.")
        return None

    try:
        import higgsfield_client
        # Higgsfield 인증: 스레드 안전을 위해 클라이언트 설정 사용
        if hasattr(higgsfield_client, "configure"):
            higgsfield_client.configure(api_key=hf_key, account_id=hf_account or "")
        else:
            # 레거시 SDK: configure() 미지원 시 경고 후 중단
            # (os.environ 직접 변경은 스레드 안전하지 않으므로 제거)
            print("[Higgsfield 오류] SDK가 configure() 미지원. higgsfield-client를 최신 버전으로 업데이트하세요.")
            return None
    except ImportError:
        print("[Higgsfield 오류] higgsfield-client 패키지가 없습니다. (pip install higgsfield-client)")
        return None

    print(f"-> [{engine_name}] 컷 {index+1} 이미지-투-비디오 렌더링 요청 중 (Higgsfield)...")

    try:
        # 이미지 업로드
        from PIL import Image
        img = Image.open(image_path)
        img_url = higgsfield_client.upload_image(img)

        # 비디오 생성 요청
        result = higgsfield_client.subscribe(
            f"{model_id}/image-to-video",
            arguments={
                "image": img_url,
                "prompt": f"Cinematic movement, 4k, realistic physics. {prompt}",
                "duration": 5,
            },
        )

        # 결과에서 비디오 URL 추출
        video_url = None
        if isinstance(result, dict):
            video_url = result.get("url") or result.get("video_url")
            if not video_url and "videos" in result:
                videos = result["videos"]
                if videos:
                    video_url = videos[0].get("url")

        if not video_url:
            print(f"[{engine_name} 오류] 비디오 URL을 받지 못했습니다. 응답: {str(result)[:200]}")
            return None

        return _download_video(video_url, index, topic_folder, engine)

    except Exception as e:
        err_str = str(e)
        if "Internal Server Error" in err_str:
            print(f"[{engine_name} 오류] Higgsfield 서버 오류 - 크레딧 부족 또는 서비스 일시 중단일 수 있습니다.")
        else:
            print(f"[{engine_name} 오류] Higgsfield API 호출 실패: {e}")
        return None


def _generate_via_openai_sora(
    image_path: str, prompt: str, index: int, topic_folder: str
) -> str | None:
    """OpenAI Sora 2 API를 통한 비디오 생성"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("[Sora 2 오류] OPENAI_API_KEY가 없습니다.")
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
    except Exception as e:
        print(f"[Sora 2 오류] 클라이언트 초기화 실패: {e}")
        return None

    print(f"-> [Sora 2] 컷 {index+1} 이미지-투-비디오 렌더링 요청 중...")

    # 이미지 크기 제한
    file_size = os.path.getsize(image_path)
    if file_size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
        print(f"[Sora 2 오류] 이미지가 너무 큽니다 ({file_size // 1024 // 1024}MB, 최대 {MAX_IMAGE_SIZE_MB}MB)")
        return None

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    mime_type = mimetypes.guess_type(image_path)[0] or "image/png"

    try:
        response = client.responses.create(
            model="sora",
            input=[
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{img_b64}"}},
                {"type": "text", "text": f"Generate a 5-second cinematic video with smooth camera movement. {prompt}"},
            ],
            tools=[{"type": "video_generation", "resolution": "1080p", "duration": 5}],
        )

        video_url = None
        for output in response.output:
            if hasattr(output, "type") and output.type == "video_generation_call":
                poll_interval = SORA_POLL_INTERVAL
                poll_start = time.time()
                for poll_count in range(SORA_MAX_POLLS):
                    time.sleep(poll_interval)
                    try:
                        status = client.responses.retrieve(response.id)
                        for out in status.output:
                            if hasattr(out, "url") and out.url:
                                video_url = out.url
                                break
                        if video_url:
                            break
                    except (ConnectionError, TimeoutError):
                        continue
                    except Exception as poll_err:
                        err_msg = str(poll_err)
                        if "401" in err_msg or "403" in err_msg or "invalid_api_key" in err_msg:
                            print(f"[Sora 2 인증 오류] 폴링 중 인증 실패 — 중단합니다: {poll_err}")
                            return None
                        continue
                    # 30초마다 진행 상태 로그
                    if (poll_count + 1) % 6 == 0:
                        elapsed = int(time.time() - poll_start)
                        print(f"  [Sora 2] 컷 {index+1} 렌더링 대기 중... ({elapsed}초 경과)")
                    # 1분 이후 폴링 간격 확대
                    if poll_count == SORA_SLOWDOWN_AT:
                        poll_interval = SORA_POLL_INTERVAL_SLOW

        if not video_url:
            print(f"[Sora 2 오류] 컷 {index+1} 비디오 생성 실패 또는 타임아웃.")
            return None

    except Exception as e:
        print(f"[Sora 2 오류] API 호출 실패: {e}")
        return None

    return _download_video(video_url, index, topic_folder, "sora2")


def _generate_via_kling_direct(
    image_path: str, prompt: str, index: int, topic_folder: str
) -> str | None:
    """기존 Kling AI 직접 연동"""
    from modules.video.kling import generate_video_from_image as kling_generate
    return kling_generate(image_path, prompt, index, topic_folder)


def _download_video(
    video_url: str, index: int, topic_folder: str, engine: str
) -> str | None:
    """생성된 비디오를 로컬에 다운로드합니다."""
    output_dir = os.path.join("assets", topic_folder, "video_clips")
    os.makedirs(output_dir, exist_ok=True)
    final_path = os.path.join(output_dir, f"{engine}_cut_{index:02d}.mp4")

    engine_name = SUPPORTED_ENGINES.get(engine, {}).get("name", engine)
    try:
        print(f"-> [{engine_name}] 컷 {index+1} 렌더링 완료! 비디오 다운로드 중...")
        vid_resp = requests.get(video_url, stream=True, timeout=VIDEO_DOWNLOAD_TIMEOUT)
        vid_resp.raise_for_status()
        with open(final_path, "wb") as f:
            for chunk in vid_resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return final_path
    except Exception as e:
        print(f"[{engine_name} 다운로드 오류] 컷 {index+1} 저장 실패: {e}")
        return None
