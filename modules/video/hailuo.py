"""
HailuoAI (MiniMax) 비디오 생성 모듈
- Image-to-Video: 정지 이미지 → 5초 비디오
- API: MiniMax Video Generation API
- 인증: Bearer token (HAILUO_API_KEY)
"""

import os
import time
import random
import tempfile
import base64
import requests


# 폴링 설정
MAX_WAIT = 420       # 절대 타임아웃 7분
MAX_POLLS = 60       # 최대 폴링 횟수
MAX_IMAGE_SIZE_MB = 20


def generate_video_from_image(
    image_path: str,
    prompt: str,
    index: int,
    topic_folder: str,
    description: str = "",
) -> str | None:
    """
    HailuoAI (MiniMax)를 사용하여 정지 이미지를 비디오로 변환합니다.
    """
    api_key = os.getenv("HAILUO_API_KEY")
    if not api_key:
        print("[HailuoAI 오류] HAILUO_API_KEY가 없습니다.")
        return None

    if not os.path.exists(image_path):
        print(f"[HailuoAI 오류] 이미지를 찾을 수 없습니다: {image_path}")
        return None

    # 이미지 크기 제한
    file_size = os.path.getsize(image_path)
    if file_size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
        print(f"[HailuoAI 오류] 이미지가 너무 큽니다 ({file_size // 1024 // 1024}MB, 최대 {MAX_IMAGE_SIZE_MB}MB)")
        return None

    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    # 1. 태스크 제출
    submit_url = "https://api.minimax.chat/v1/video_generation"
    payload = {
        "model": "video-01-live2d",
        "prompt": prompt,
        "first_frame_image": f"data:image/png;base64,{img_b64}",
    }

    print(f"-> [HailuoAI] 컷 {index + 1} 이미지-투-비디오 렌더링 요청 중...")
    task_id = None
    MAX_RETRIES = 3
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(submit_url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            resp_data = resp.json()

            # MiniMax API 에러 체크
            if resp_data.get("base_resp", {}).get("status_code", 0) != 0:
                err_msg = resp_data.get("base_resp", {}).get("status_msg", "알 수 없는 오류")
                print(f"[HailuoAI 오류] 생성 요청 거절됨: {err_msg}")
                return None

            task_id = resp_data.get("task_id")
            if not task_id:
                print("[HailuoAI 오류] task_id를 받지 못했습니다.")
                return None
            break
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait = min(2 ** (attempt + 1), 15) + random.uniform(0, 2)
                print(f"[HailuoAI 재시도] {attempt + 1}/{MAX_RETRIES} — {wait:.1f}초 대기")
                time.sleep(wait)
            else:
                print(f"[HailuoAI 오류] 최대 재시도 초과: {e}")
                return None

    # 2. 결과 폴링 대기 (task_id는 retry loop에서 보장되지만 방어적 체크)
    if not task_id:
        return None
    poll_url = f"https://api.minimax.chat/v1/query/video_generation?task_id={task_id}"
    file_id = None

    print(f"-> [HailuoAI] 컷 {index + 1} 렌더링 클라우드 진행 상태 대기 중 (약 2~4분 소요 예상)...")

    _elapsed = 0
    timed_out = True
    for poll_iter in range(MAX_POLLS):
        # 적응형 폴링: 초반 5초 → 1분후 10초 → 2분후 15초
        _poll_wait = 5 if _elapsed < 60 else (10 if _elapsed < 120 else 15)
        time.sleep(_poll_wait)
        _elapsed += _poll_wait
        if _elapsed >= MAX_WAIT:
            break

        try:
            poll_resp = requests.get(poll_url, headers=headers, timeout=30)
            poll_resp.raise_for_status()
            poll_data = poll_resp.json()

            status = poll_data.get("status", "")

            if status == "Success":
                file_id = poll_data.get("file_id")
                timed_out = False
                break
            elif status == "Fail":
                reason = poll_data.get("base_resp", {}).get("status_msg", "알 수 없는 오류")
                print(f"[HailuoAI 오류] 컷 {index + 1} 클라우드 렌더링 실패: {reason}")
                return None
            # Queueing, Processing → 계속 대기

            if poll_iter > 0 and poll_iter % 12 == 0:
                print(f"  [HailuoAI] 컷 {index + 1} 렌더링 진행 중... ({_elapsed}초 경과, 상태: {status})")

        except requests.exceptions.HTTPError as e:
            if hasattr(e, "response") and e.response is not None and e.response.status_code in (401, 403):
                print(f"[HailuoAI 인증 오류] API 키 인증 실패 — 중단합니다.")
                return None
            print(f"[HailuoAI 대기 중 오류] {e}")
            continue
        except Exception as e:
            print(f"[HailuoAI 대기 중 오류] {e}")
            continue

    if not file_id:
        if timed_out:
            print(f"[HailuoAI 오류] 컷 {index + 1} 렌더링 타임아웃 ({_elapsed}초 경과).")
        else:
            print(f"[HailuoAI 오류] 컷 {index + 1} 렌더링 성공했으나 file_id가 비어 있습니다.")
        return None

    # 3. 파일 다운로드
    download_url = f"https://api.minimax.chat/v1/files/retrieve?file_id={file_id}"
    output_dir = os.path.join("assets", topic_folder, "hailuo_videos")
    os.makedirs(output_dir, exist_ok=True)
    final_video_path = os.path.join(output_dir, f"hailuo_cut_{index:02d}.mp4")

    tmp_path = None
    try:
        print(f"-> [HailuoAI] 컷 {index + 1} 렌더링 완료! 비디오 다운로드 중...")
        vid_resp = requests.get(download_url, headers=headers, stream=True, timeout=60)
        vid_resp.raise_for_status()
        fd, tmp_path = tempfile.mkstemp(dir=output_dir, suffix=".tmp")
        os.close(fd)
        _MAX_DOWNLOAD_SIZE = 500 * 1024 * 1024  # 500MB
        downloaded = 0
        with open(tmp_path, "wb") as f:
            for chunk in vid_resp.iter_content(chunk_size=8192):
                downloaded += len(chunk)
                if downloaded > _MAX_DOWNLOAD_SIZE:
                    raise RuntimeError(f"비디오 다운로드 크기 초과 ({downloaded // (1024 * 1024)}MB > 500MB)")
                f.write(chunk)
        os.replace(tmp_path, final_video_path)
        return final_video_path
    except Exception as e:
        print(f"[HailuoAI 다운로드 오류] 컷 {index + 1} 저장 실패: {e}")
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return None
