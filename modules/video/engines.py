"""
멀티 비디오 엔진 통합 모듈
Higgsfield 통합 API를 통해 Kling, Sora 2, Veo 3, Hailuo 등을 지원하며,
기존 Kling 직접 연동도 폴백으로 유지합니다.
"""

import os
import time
import requests
import base64

# 지원 엔진 목록 (프론트엔드 드롭다운용)
SUPPORTED_ENGINES = {
    "kling": {"name": "Kling 3.0", "desc": "시네마틱 모션 (기본)", "provider": "higgsfield"},
    "sora2": {"name": "Sora 2", "desc": "최고 품질 (OpenAI)", "provider": "openai"},
    "veo3": {"name": "Veo 3.1", "desc": "4K 시네마틱 (Google)", "provider": "higgsfield"},
    "hailuo": {"name": "Hailuo 2.3", "desc": "가성비 최고 (Minimax)", "provider": "higgsfield"},
    "wan": {"name": "Wan 2.5", "desc": "빠른 생성 (Alibaba)", "provider": "higgsfield"},
    "none": {"name": "비디오 없음", "desc": "정지 이미지만 사용", "provider": "none"},
}

# Higgsfield 엔진 → 모델 ID 매핑
_HIGGSFIELD_MODELS = {
    "kling": "kling-v2-master",
    "veo3": "veo-3",
    "hailuo": "hailuo-02",
    "wan": "wan-2.1",
}


def get_available_engines() -> list[dict]:
    """프론트엔드에 표시할 사용 가능한 엔진 목록을 반환합니다."""
    available = []
    for key, info in SUPPORTED_ENGINES.items():
        available.append({"id": key, **info})
    return available


def generate_video_from_image(
    image_path: str,
    prompt: str,
    index: int,
    topic_folder: str,
    engine: str = "kling",
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

    if engine == "sora2":
        return _generate_via_openai_sora(image_path, prompt, index, topic_folder)

    if engine in _HIGGSFIELD_MODELS:
        result = _generate_via_higgsfield(image_path, prompt, index, topic_folder, engine)
        if result:
            return result
        # Higgsfield 실패 시 기존 Kling 직접 연동으로 폴백
        if engine == "kling":
            print(f"-> [폴백] Higgsfield 실패, Kling 직접 API로 재시도...")
            return _generate_via_kling_direct(image_path, prompt, index, topic_folder)
        return None

    print(f"[비디오 엔진 오류] 알 수 없는 엔진: {engine}")
    return None


def _generate_via_higgsfield(
    image_path: str, prompt: str, index: int, topic_folder: str, engine: str
) -> str | None:
    """Higgsfield 통합 API를 통한 비디오 생성"""
    api_key = os.getenv("HIGGSFIELD_API_KEY")
    account_id = os.getenv("HIGGSFIELD_ACCOUNT_ID")

    if not api_key or not account_id:
        print("[Higgsfield 오류] API_KEY 또는 ACCOUNT_ID가 없습니다.")
        return None

    model_id = _HIGGSFIELD_MODELS.get(engine)
    engine_name = SUPPORTED_ENGINES[engine]["name"]

    try:
        from higgsfield import HiggsClient

        client = HiggsClient(api_key=api_key, account_id=account_id)
    except ImportError:
        print("[Higgsfield 오류] higgsfield-client 패키지가 없습니다. (pip install higgsfield-client)")
        return None
    except Exception as e:
        print(f"[Higgsfield 오류] 클라이언트 초기화 실패: {e}")
        return None

    print(f"-> [{engine_name}] 컷 {index+1} 이미지-투-비디오 렌더링 요청 중 (Higgsfield)...")

    try:
        result = client.subscribe(
            endpoint="image-to-video",
            params={
                "model": model_id,
                "image": image_path,
                "prompt": f"Cinematic movement, 4k, realistic physics. {prompt}",
                "duration": 5,
            },
        )

        if not result or not hasattr(result, "url"):
            print(f"[{engine_name} 오류] 비디오 URL을 받지 못했습니다.")
            return None

        video_url = result.url

    except Exception as e:
        print(f"[{engine_name} 오류] Higgsfield API 호출 실패: {e}")
        return None

    # 비디오 로컬 다운로드
    return _download_video(video_url, index, topic_folder, engine)


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

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    try:
        response = client.responses.create(
            model="sora",
            input=[
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                },
                {
                    "type": "text",
                    "text": f"Generate a 5-second cinematic video with smooth camera movement. {prompt}",
                },
            ],
            tools=[
                {
                    "type": "video_generation",
                    "resolution": "1080p",
                    "duration": 5,
                }
            ],
        )

        # Sora 응답에서 비디오 URL 추출
        video_url = None
        for output in response.output:
            if hasattr(output, "type") and output.type == "video_generation_call":
                # 비디오 생성 결과 폴링
                generation_id = output.id
                # 생성 완료 대기
                for _ in range(120):
                    time.sleep(5)
                    try:
                        status = client.responses.retrieve(response.id)
                        for out in status.output:
                            if hasattr(out, "url") and out.url:
                                video_url = out.url
                                break
                        if video_url:
                            break
                    except Exception:
                        continue

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
    """기존 Kling AI 직접 연동 (폴백용)"""
    from modules.video.kling import generate_video_from_image as kling_generate

    return kling_generate(image_path, prompt, index, topic_folder)


def _download_video(
    video_url: str, index: int, topic_folder: str, engine: str
) -> str | None:
    """생성된 비디오를 로컬에 다운로드합니다."""
    output_dir = os.path.join("assets", topic_folder, "video_clips")
    os.makedirs(output_dir, exist_ok=True)
    final_path = os.path.join(output_dir, f"{engine}_cut_{index:02d}.mp4")

    try:
        engine_name = SUPPORTED_ENGINES.get(engine, {}).get("name", engine)
        print(f"-> [{engine_name}] 컷 {index+1} 렌더링 완료! 비디오 다운로드 중...")
        vid_resp = requests.get(video_url, stream=True, timeout=60)
        with open(final_path, "wb") as f:
            for chunk in vid_resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return final_path
    except Exception as e:
        engine_name = SUPPORTED_ENGINES.get(engine, {}).get("name", engine)
        print(f"[{engine_name} 다운로드 오류] 컷 {index+1} 저장 실패: {e}")
        return None
