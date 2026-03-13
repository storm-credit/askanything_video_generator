import io
import os
import time

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
                # 안전 정책 위반(Safety Policy) 에러 처리 로직
                if 'content_policy_violation' in error_msg:
                    print(f"  [DALL·E 경고] 컷 {index+1} 정책 위반 감지. 아주 안전하고 추상적인 대체 프롬프트로 재시도합니다... ({attempt+1}/{max_retries})")
                    # DALL-E 3 가 무조건 통과시킬 만한 완전 기초적인 대체(fallback) 프롬프트로 강제 치환
                    enhanced_prompt = "A very safe, beautiful, abstract and highly detailed cinematic visualization illustrating the related concept, National Geographic high-end documentary style, atmospheric lighting, strictly NO TEXT, NO LETTERS, NO WORDS."
                else:
                    print(f"  [DALL·E 경고] 컷 {index+1} 렌더링 실패. 서버 지연으로 3초 후 재시도합니다... ({attempt+1}/{max_retries}) | 사유: {e}")
                time.sleep(3)
            else:
                raise RuntimeError(f"[DALL·E 이미지 생성 최종 실패] index={index}, 3회 재시도 실패. 오류: {error_msg}")
