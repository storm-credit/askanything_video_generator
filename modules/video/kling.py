import os
import time
import random
import jwt
import requests
import base64


def _get_motion_style(prompt: str) -> str:
    """감정 태그 기반 모션 스타일 결정"""
    if "[SHOCK]" in prompt or "shock" in prompt.lower():
        return "fast dynamic camera movement, sudden dramatic angles"
    elif "[WONDER]" in prompt or "wonder" in prompt.lower():
        return "slow graceful panning, gentle reveal shots"
    elif "[TENSION]" in prompt or "tension" in prompt.lower():
        return "slow creeping approach, tightening frame"
    elif "[CALM]" in prompt or "calm" in prompt.lower():
        return "very slow or static camera, peaceful ambient motion"
    elif "[REVEAL]" in prompt or "reveal" in prompt.lower():
        return "sudden camera shift, dramatic angle change"
    else:
        return "smooth cinematic camera movement"


def _generate_jwt(ak: str, sk: str) -> str:
    headers = {
        "alg": "HS256",
        "typ": "JWT"
    }
    payload = {
        "iss": ak,
        "exp": int(time.time()) + 1800,  # 30분 만료
        "nbf": int(time.time()) - 5      # 5초 전 활성화
    }
    return jwt.encode(payload, sk, headers=headers)

def generate_video_from_image(image_path: str, prompt: str, index: int, topic_folder: str, ak_override: str = None, sk_override: str = None) -> str | None:
    """
    Kling AI를 사용하여 정지 이미지를 5초짜리 시네마틱 숏폼 비디오로 변환합니다.
    """
    ak = ak_override or os.getenv("KLING_ACCESS_KEY")
    sk = sk_override or os.getenv("KLING_SECRET_KEY")
    
    if not ak or not sk:
        print("[Kling AI 오류] KLING_ACCESS_KEY 또는 KLING_SECRET_KEY가 없습니다.")
        return None
        
    if not os.path.exists(image_path):
        print(f"[Kling AI 오류] 이미지를 찾을 수 없습니다: {image_path}")
        return None
        
    try:
        token = _generate_jwt(ak, sk)
    except Exception as e:
        print(f"[Kling AI 오류] JWT 발급 실패: {e}")
        return None
        
    # 이미지 Base64 인코딩 (20MB 제한)
    file_size = os.path.getsize(image_path)
    if file_size > 20 * 1024 * 1024:
        print(f"[Kling AI 오류] 이미지가 너무 큽니다 ({file_size // 1024 // 1024}MB, 최대 20MB)")
        return None
    with open(image_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")
        
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    # 1. 태스크 제출
    submit_url = "https://api.klingai.com/v1/videos/image2video"
    payload = {
        "model": "kling-v1",
        "image": img_b64,
        "prompt": f"{_get_motion_style(prompt)}, 4k, realistic physics. {prompt}",
        "duration": "5"
    }
    
    print(f"-> [Kling AI] 컷 {index+1} 이미지-투-비디오 렌더링 요청 중...")
    task_id = None
    MAX_RETRIES = 3
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(submit_url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
            resp_data = resp.json()

            if resp_data.get("code") != 0:
                print(f"[Kling AI 오류] 생성 요청 거절됨: {resp_data}")
                return None

            task_id = resp_data.get("data", {}).get("task_id")
            if not task_id:
                print(f"[Kling AI 오류] task_id를 받지 못했습니다.")
                return None
            break
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                wait = min(2 ** (attempt + 1), 15) + random.uniform(0, 2)
                print(f"[Kling 재시도] {attempt+1}/{MAX_RETRIES} — {wait:.1f}초 대기")
                time.sleep(wait)
            else:
                print(f"[Kling 오류] 최대 재시도 초과: {e}")
                return None
        
    # 2. 결과 폴링 대기
    poll_url = f"https://api.klingai.com/v1/videos/image2video/{task_id}"
    video_url = None
    
    print(f"-> [Kling AI] 컷 {index+1} 렌더링 클라우드 진행 상태 대기 중 (약 2~3분 소요 예상)...")
    
    max_polls = 90  # 90 * 5초 = 450초 (7.5분)
    timed_out = True
    for poll_iter in range(max_polls):
        if poll_iter > 0:
            time.sleep(5)

        try:
            poll_resp = requests.get(poll_url, headers=headers, timeout=30)
            poll_resp.raise_for_status()
            poll_data = poll_resp.json()

            status = poll_data.get("data", {}).get("task_status")

            if status == "succeed":
                videos = poll_data.get("data", {}).get("task_result", {}).get("videos", [])
                if videos:
                    video_url = videos[0].get("url") or videos[0].get("video_url")
                timed_out = False
                break
            elif status == "failed":
                reason = poll_data.get("data", {}).get("task_status_msg", "알 수 없는 오류")
                print(f"[Kling AI 오류] 컷 {index+1} 클라우드 렌더링 실패: {reason}")
                return None
            # processing/pending/submitted → 계속 대기

            if poll_iter > 0 and poll_iter % 12 == 0:
                elapsed = (poll_iter + 1) * 5
                print(f"  [Kling AI] 컷 {index+1} 렌더링 진행 중... ({elapsed}초 경과, 상태: {status})")

        except Exception as e:
            print(f"[Kling AI 대기 중 오류] {e}")
            continue

    if not video_url:
        if timed_out:
            print(f"[Kling AI 오류] 컷 {index+1} 렌더링 타임아웃 (최대 {max_polls * 5}초 초과).")
        else:
            print(f"[Kling AI 오류] 컷 {index+1} 렌더링 성공했으나 비디오 URL이 비어 있습니다.")
        return None
        
    # 3. 비디오 로컬 다운로드
    output_dir = os.path.join("assets", topic_folder, "kling_videos")
    os.makedirs(output_dir, exist_ok=True)
    final_video_path = os.path.join(output_dir, f"kling_cut_{index:02d}.mp4")
    
    try:
        print(f"-> [Kling AI] 컷 {index+1} 렌더링 완료! 비디오 다운로드 중...")
        vid_resp = requests.get(video_url, stream=True, timeout=30)
        vid_resp.raise_for_status()
        with open(final_video_path, "wb") as f:
            for chunk in vid_resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return final_video_path
    except Exception as e:
        print(f"[Kling AI 다운로드 오류] 컷 {index+1} 저장 실패: {e}")
        return None
