import io
import os
import shutil
import time
import random

import requests
from openai import OpenAI
from PIL import Image, ImageOps

from modules.utils.constants import MASTER_STYLE
from modules.utils.cache import get_cached_image, save_to_cache
from modules.utils.safety import is_safety_error, get_safety_fallback_prompt

def generate_image(prompt: str, index: int, topic_folder: str = "default_topic", api_key: str | None = None) -> str:
    final_api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not final_api_key:
        raise EnvironmentError("OpenAI API 키가 제공되지 않았습니다.")
    
    client = OpenAI(api_key=final_api_key)

    if not prompt or not prompt.strip():
        raise ValueError(f"[DALL·E 이미지 오류] 프롬프트가 비어 있습니다 (index={index})")

    enhanced_prompt = MASTER_STYLE + prompt

    # ── 캐시 확인 ──
    cached = get_cached_image(enhanced_prompt)
    if cached:
        image_dir = f"assets/{topic_folder}/images"
        os.makedirs(image_dir, exist_ok=True)
        filename = os.path.join(image_dir, f"cut_{index:02}.png")
        shutil.copy2(cached, filename)
        print(f"[이미지 캐시] 히트 — 재생성 스킵 (컷 {index+1})")
        return filename

    safety_retry_count = 0  # safety fallback stage tracker

    max_retries = 3
    for attempt in range(max_retries):
        try:
            if attempt == 0:
                print(f"-> [아트 디렉터] 컷 {index+1} 마스터 렌더링 중...")

            response = client.images.generate(
                model="dall-e-3",
                prompt=enhanced_prompt,
                size="1024x1792",
                n=1,
                quality="standard"
            )
            image_url = response.data[0].url
            img_resp = requests.get(image_url, timeout=30)
            img_resp.raise_for_status()
            image_data = img_resp.content

            image = Image.open(io.BytesIO(image_data)).convert("RGB")
            target_size = (1080, 1920)
            fitted_image = ImageOps.fit(image, target_size, method=Image.LANCZOS, centering=(0.5, 0.5))

            image_dir = f"assets/{topic_folder}/images"
            os.makedirs(image_dir, exist_ok=True)
            filename = os.path.join(image_dir, f"cut_{index:02}.png")
            fitted_image.save(filename)

            save_to_cache(enhanced_prompt, filename)
            return filename

        except Exception as e:
            error_msg = str(e)
            if attempt < max_retries - 1:
                if is_safety_error(error_msg):
                    enhanced_prompt = get_safety_fallback_prompt(prompt, safety_retry_count)
                    safety_retry_count += 1
                    print(f"  [DALL·E 경고] 컷 {index+1} 정책 위반 감지. 대체 프롬프트로 재시도합니다... ({attempt+1}/{max_retries})")
                elif '429' in error_msg or 'rate_limit' in error_msg.lower():
                    wait = min(2 ** (attempt + 1), 30) + random.uniform(0, 2)
                    print(f"  [DALL·E 429] 컷 {index+1} 속도 제한. {wait:.1f}초 후 재시도... ({attempt+1}/{max_retries})")
                    time.sleep(wait)
                    continue
                else:
                    print(f"  [DALL·E 경고] 컷 {index+1} 렌더링 실패. 3초 후 재시도합니다... ({attempt+1}/{max_retries}) | 사유: {e}")
                    enhanced_prompt = MASTER_STYLE + prompt
                time.sleep(min(2 ** (attempt + 1), 10) + random.uniform(0, 1))
            else:
                raise RuntimeError(f"[DALL·E 이미지 생성 최종 실패] index={index}, 3회 재시도 실패. 오류: {error_msg}")
