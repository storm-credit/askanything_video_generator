from openai import OpenAI
import requests
from PIL import Image, ImageOps
import io
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def generate_image(prompt, index, topic_folder="default_topic"):
    # ✅ 프롬프트 유효성 검사
    if not prompt or not prompt.strip():
        raise ValueError(f"[DALL·E 이미지 오류] 프롬프트가 비어 있습니다 (index={index})")

    try:
        # ✅ 이미지 생성 요청
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            n=1,
            quality="standard"
        )
        image_url = response.data[0].url
        image_data = requests.get(image_url).content

        # ✅ 이미지 로딩 및 쇼츠용 비율 맞춤 (9:16 crop)
        image = Image.open(io.BytesIO(image_data)).convert("RGB")
        target_size = (1080, 1920)
        fitted_image = ImageOps.fit(image, target_size, method=Image.LANCZOS, centering=(0.5, 0.5))  # 꽉 차게 자르기

        # ✅ 이미지 저장
        image_dir = f"assets/{topic_folder}/images"
        os.makedirs(image_dir, exist_ok=True)
        filename = os.path.join(image_dir, f"cut_{index:02}.png")
        fitted_image.save(filename)

        return filename

    except Exception as e:
        raise RuntimeError(f"[DALL·E 이미지 생성 실패] index={index}, 오류: {str(e)}")
