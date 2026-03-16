import io
import os
import time
import random

import requests
from openai import OpenAI
from PIL import Image, ImageOps

from modules.utils.constants import MASTER_STYLE

def generate_image(prompt: str, index: int, topic_folder: str = "default_topic", api_key: str | None = None) -> str:
    final_api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not final_api_key:
        raise EnvironmentError("OpenAI API 키가 제공되지 않았습니다.")
    
    client = OpenAI(api_key=final_api_key)

    if not prompt or not prompt.strip():
        raise ValueError(f"[DALL·E 이미지 오류] 프롬프트가 비어 있습니다 (index={index})")

    enhanced_prompt = MASTER_STYLE + prompt

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

            return filename

        except Exception as e:
            error_msg = str(e)
            if attempt < max_retries - 1:
                if 'content_policy_violation' in error_msg:
                    print(f"  [DALL·E 경고] 컷 {index+1} 정책 위반 감지. 대체 프롬프트로 재시도합니다... ({attempt+1}/{max_retries})")
                    enhanced_prompt = "A very safe, beautiful, abstract and highly detailed cinematic visualization illustrating the related concept, National Geographic high-end documentary style, atmospheric lighting, strictly NO TEXT, NO LETTERS, NO WORDS."
                elif '429' in error_msg or 'rate_limit' in error_msg.lower():
                    wait = min(2 ** (attempt + 1), 30) + random.uniform(0, 2)
                    print(f"  [DALL·E 429] 컷 {index+1} 속도 제한. {wait:.1f}초 후 재시도... ({attempt+1}/{max_retries})")
                    time.sleep(wait)
                    continue
                else:
                    print(f"  [DALL·E 경고] 컷 {index+1} 렌더링 실패. 3초 후 재시도합니다... ({attempt+1}/{max_retries}) | 사유: {e}")
                # 안전 정책 위반이 아닌 경우 원본 프롬프트 복원
                if 'content_policy_violation' not in error_msg:
                    enhanced_prompt = MASTER_STYLE + prompt
                time.sleep(min(2 ** (attempt + 1), 10) + random.uniform(0, 1))
            else:
                raise RuntimeError(f"[DALL·E 이미지 생성 최종 실패] index={index}, 3회 재시도 실패. 오류: {error_msg}")
