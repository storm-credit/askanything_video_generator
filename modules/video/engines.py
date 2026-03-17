"""
멀티 비디오 엔진 통합 모듈
- Veo 3: Google genai SDK 직접 연동 (Gemini 키 사용)
- Sora 2: OpenAI API 직접 연동
- Kling: Kling AI 직접 연동 (KLING_ACCESS_KEY/SECRET_KEY)
"""

import os
import tempfile
import time
import mimetypes
import requests
import base64

# 지원 엔진 목록 (프론트엔드 드롭다운용)
SUPPORTED_ENGINES = {
    "kling": {"name": "Kling 3.0", "desc": "시네마틱 모션", "provider": "kling_direct"},
    "sora2": {"name": "Sora 2", "desc": "최고 품질 (OpenAI)", "provider": "openai"},
    "veo3": {"name": "Veo 3", "desc": "Google API 직접 연동", "provider": "google"},
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

from modules.utils.constants import get_motion_style


def _optimize_prompt_for_engine(engine: str, prompt: str, description: str = "") -> str:
    """엔진별 최적화된 비디오 프롬프트를 생성합니다 (논문 기반).
    - Veo: 구조화된 프롬프트 (카메라·조명·동작 명시)
    - Kling: 최소화 프롬프트 (주체 + 단일 동작)
    - Sora: 동작 벡터 중심 프롬프트
    """
    motion = get_motion_style(prompt, description)

    if engine == "veo3":
        # Veo responds best to structured prompts with explicit camera + start/end state
        return f"{motion}. {prompt}. Cinematic lighting, smooth transition, 4K quality."

    if engine == "kling":
        # Kling is sensitive to over-specification — keep it minimal
        # Extract core subject and single motion verb
        words = prompt.split(",")
        core = words[0].strip() if words else prompt
        return f"{core}, {motion.split(',')[0].strip().lower()}"

    if engine == "sora2":
        # Sora thinks in motion vectors — emphasize forces and movement
        return f"{motion}, 4K quality. {prompt}"

    return f"{motion}. {prompt}"


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
        return False, "KLING_ACCESS_KEY + KLING_SECRET_KEY 필요"

    return False, f"알 수 없는 엔진: {engine}"


def _get_available_engines(preferred_engine: str) -> list[str]:
    """Return engine list ordered by availability. Preferred engine first if available."""
    from modules.utils.keys import get_google_key

    available = []

    # Check each engine's key availability
    engine_checks = {
        "veo3": lambda: get_google_key(service="veo3") is not None,
        "kling": lambda: bool(os.getenv("KLING_ACCESS_KEY")),
        "sora2": lambda: bool(os.getenv("OPENAI_API_KEY")),
    }

    # Preferred engine first
    if preferred_engine in engine_checks:
        if engine_checks[preferred_engine]():
            available.append(preferred_engine)

    # Then other engines
    for eng, check in engine_checks.items():
        if eng != preferred_engine:
            try:
                if check():
                    available.append(eng)
            except Exception as _chk_err:
                print(f"[엔진 체크 경고] {eng} 가용성 확인 실패: {_chk_err}")

    return available


def generate_video_from_image(
    image_path: str,
    prompt: str,
    index: int,
    topic_folder: str,
    engine: str = "kling",
    google_api_key: str = None,
    description: str = "",
    veo_model: str | None = None,
    gemini_api_keys: str | None = None,
) -> str | None:
    """
    선택된 엔진으로 이미지를 비디오로 변환합니다.
    키 가용성에 따라 동적 폴백을 시도합니다.
    모든 엔진 실패 시 None을 반환합니다 (호출자가 정지 이미지로 폴백).
    """
    if engine == "none":
        return None

    if not os.path.exists(image_path):
        print(f"[비디오 엔진 오류] 이미지를 찾을 수 없습니다: {image_path}")
        return None

    # Build dynamic engine order based on key availability
    engines_to_try = _get_available_engines(engine)
    print(f"[비디오 엔진] 사용 가능: {engines_to_try}")

    if not engines_to_try:
        print(f"[비디오 엔진 오류] 사용 가능한 엔진이 없습니다. 정지 이미지로 폴백합니다.")
        return None

    for eng in engines_to_try:
        result = _try_engine(eng, image_path, prompt, index, topic_folder, google_api_key, description=description, veo_model=veo_model, gemini_api_keys=gemini_api_keys)
        if result is not None:
            return result
        print(f"[비디오 엔진] {eng} 실패 → 다음 엔진 시도")

    print(f"[비디오 엔진] 모든 엔진 실패. 정지 이미지로 폴백합니다.")
    return None


def _try_engine(
    engine: str,
    image_path: str,
    prompt: str,
    index: int,
    topic_folder: str,
    google_api_key: str = None,
    description: str = "",
    veo_model: str | None = None,
    gemini_api_keys: str | None = None,
) -> str | None:
    """단일 엔진으로 비디오 생성을 시도합니다. 엔진별 프롬프트 최적화 적용."""
    optimized_prompt = _optimize_prompt_for_engine(engine, prompt, description)
    try:
        if engine == "veo3":
            from modules.video.veo import generate_video_veo
            return generate_video_veo(image_path, optimized_prompt, index, topic_folder, google_api_key, description=description, model_override=veo_model, gemini_api_keys=gemini_api_keys)

        if engine == "sora2":
            return _generate_via_openai_sora(image_path, optimized_prompt, index, topic_folder, description=description)

        if engine == "kling":
            return _generate_via_kling_direct(image_path, optimized_prompt, index, topic_folder, description=description)
    except Exception as e:
        print(f"[비디오 엔진 오류] {engine} 예외: {e}")
        return None

    print(f"[비디오 엔진 오류] 알 수 없는 엔진: {engine}")
    return None


def _generate_via_openai_sora(
    image_path: str, prompt: str, index: int, topic_folder: str, description: str = ""
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
                {"type": "text", "text": f"{get_motion_style(prompt, description)}, 4K quality. {prompt}"},
            ],
            tools=[{"type": "video_generation", "resolution": "1080p", "duration": 8}],
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
                    except (ConnectionError, TimeoutError, OSError):
                        # OSError: 네트워크 오류 상위 클래스 (OpenAI SDK 래핑 포함)
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
    image_path: str, prompt: str, index: int, topic_folder: str, description: str = ""
) -> str | None:
    """기존 Kling AI 직접 연동"""
    from modules.video.kling import generate_video_from_image as kling_generate
    return kling_generate(image_path, prompt, index, topic_folder, description=description)


def _download_video(
    video_url: str, index: int, topic_folder: str, engine: str
) -> str | None:
    """생성된 비디오를 로컬에 다운로드합니다."""
    output_dir = os.path.join("assets", topic_folder, "video_clips")
    os.makedirs(output_dir, exist_ok=True)
    final_path = os.path.join(output_dir, f"{engine}_cut_{index:02d}.mp4")

    engine_name = SUPPORTED_ENGINES.get(engine, {}).get("name", engine)
    _MAX_DOWNLOAD_SIZE = 500 * 1024 * 1024  # 500MB safety limit
    tmp_path = None
    try:
        print(f"-> [{engine_name}] 컷 {index+1} 렌더링 완료! 비디오 다운로드 중...")
        vid_resp = requests.get(video_url, stream=True, timeout=VIDEO_DOWNLOAD_TIMEOUT)
        vid_resp.raise_for_status()
        # Write to temp file first to prevent partial downloads
        fd, tmp_path = tempfile.mkstemp(dir=output_dir, suffix=".tmp")
        os.close(fd)
        downloaded = 0
        with open(tmp_path, "wb") as f:
            for chunk in vid_resp.iter_content(chunk_size=8192):
                downloaded += len(chunk)
                if downloaded > _MAX_DOWNLOAD_SIZE:
                    raise RuntimeError(f"다운로드 크기 초과 ({downloaded // 1024 // 1024}MB > 500MB)")
                f.write(chunk)
        os.replace(tmp_path, final_path)  # atomic rename
        return final_path
    except Exception as e:
        print(f"[{engine_name} 다운로드 오류] 컷 {index+1} 저장 실패: {e}")
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return None
