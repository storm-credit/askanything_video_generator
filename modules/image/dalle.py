from openai import OpenAI
import requests
from PIL import Image, ImageOps
import io
import os
import time

def generate_image(prompt, index, topic_folder="default_topic", api_key=None):
    final_api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not final_api_key:
        raise EnvironmentError("OpenAI API 키가 제공되지 않았습니다.")
    
    client = OpenAI(api_key=final_api_key)

    if not prompt or not prompt.strip():
        raise ValueError(f"[DALL·E 이미지 오류] 프롬프트가 비어 있습니다 (index={index})")

    # ✅ 업계 최고 수준의 DALL-E 3 마스터 아트 디렉터 프리셋 (슈퍼 렌더 퀄리티 보장 및 텍스트 타이포그래피 금지)
    master_style = (
        "Award-winning 3D animation, Disney Pixar style, hyper-detailed, Octane Render, "
        "global illumination, ray tracing, cinematic dramatic lighting, breathtaking aesthetic, "
        "8k resolution, perfect center focus for vertical aspect ratio. "
        "Absolutely NO TEXT, NO LETTERS, NO WORDS, NO WATERMARKS in the image. "
    )
    enhanced_prompt = master_style + prompt

    max_retries = 3
    for attempt in range(max_retries):
        try:
            if attempt == 0:
                print(f"-> [아트 디렉터] 컷 {index+1} 마스터 렌더링 중...")
                
            response = client.images.generate(
                model="dall-e-3",
                prompt=enhanced_prompt,
                size="1024x1024",
                n=1,
                quality="standard"
            )
            image_url = response.data[0].url
            image_data = requests.get(image_url).content

            image = Image.open(io.BytesIO(image_data)).convert("RGB")
            target_size = (1080, 1920)
            fitted_image = ImageOps.fit(image, target_size, method=Image.LANCZOS, centering=(0.5, 0.5))

            image_dir = f"assets/{topic_folder}/images"
            os.makedirs(image_dir, exist_ok=True)
            filename = os.path.join(image_dir, f"cut_{index:02}.png")
            fitted_image.save(filename)

            return filename

        except Exception as e:
            if attempt < max_retries - 1:
                print(f"  [DALL·E 경고] 컷 {index+1} 렌더링 실패. 서버 지연으로 3초 후 재시도합니다... ({attempt+1}/{max_retries}) | 사유: {e}")
                time.sleep(3)
            else:
                raise RuntimeError(f"[DALL·E 이미지 생성 최종 실패] index={index}, 3회 재시도 실패. 오류: {str(e)}")
