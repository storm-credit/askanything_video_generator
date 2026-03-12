import os
import re
from typing import Any

from openai import OpenAI

from modules.utils.slugify import slugify_topic

_CUT_LINE_RE = re.compile(r"^\s*(.*?)\s-\s(.*?)\s-\s(.*)\s*$")

# ✅ 컷 자동 구성 함수
def generate_cuts(topic: str, lang: str = "ko") -> tuple[list[dict[str, Any]], str]:
    topic_folder = slugify_topic(topic, lang)

    # ✅ 저장 폴더 구조 생성
    base_path = os.path.join("assets", topic_folder)
    os.makedirs(os.path.join(base_path, "images"), exist_ok=True)
    os.makedirs(os.path.join(base_path, "audio"), exist_ok=True)
    os.makedirs(os.path.join(base_path, "video"), exist_ok=True)

    # ✅ GPT 프롬프트
    prompt_text = f"""
당신은 어린이 대상 과학 영상 콘텐츠 작가입니다.

'{topic}'에 대해 아이들이 **정확히 이해하고 궁금증을 해결할 수 있도록**, 짧은 영상 콘텐츠를 만들려고 합니다.
전체 내용을 컷 단위로 나눠 구성해주세요.

각 컷은 아래 3가지 요소를 포함합니다:

1. 설명 문장 (핵심 정보 위주로, 정확한 개념과 이유 중심)
2. 영어 이미지 프롬프트 (Midjourney 스타일, **세로형 영상(9:16)에 맞도록 vertical composition, full body 포함**, 시각적으로 명확하게 그릴 수 있도록 구체적으로) **쇼츠크기**
3. 영상용 스크립트 (TTS 및 자막용, 어린이도 이해할 수 있는 부드러운 말투)

**반드시 포함해야 할 내용:**
- 주제에 대한 **과학적 설명** (왜? 어떻게? 얼마나? 등 아이의 궁금증에 대한 답변)
- **비유나 예시**를 활용해서 쉽게 설명
- 전체 컷 수는 주제의 핵심을 설명하는 데 필요한 만큼만 자동 구성 

형식 (각 줄마다 아래처럼 작성):
[설명 문장] - [영어 이미지 프롬프트] - [영상용 스크립트]

예시:
개미는 하루에 수백 번 짧은 잠을 자요 - ant sleeping briefly many times a day, vertical composition, cartoon style, 9:16 aspect ratio - "개미는 잠깐잠깐 자요. 하루에도 몇백 번! 진짜 바쁘죠?"

※ 각 줄은 반드시 하이픈(-) 기호로 2번만 구분해주세요 (총 3항목)
"""


    print("👉 GPT 호출 시작")
    model = os.getenv("OPENAI_MODEL", "gpt-4")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("환경변수 OPENAI_API_KEY가 설정되어 있지 않습니다.")

    client = OpenAI(api_key=api_key)

    # ✅ GPT 호출
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt_text}],
    )
    print("✅ GPT 응답 수신 완료")

    content = response.choices[0].message.content.strip()

    # ✅ 파싱
    cuts = []
    for line in content.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        match = _CUT_LINE_RE.match(stripped)
        if not match:
            continue

        desc, image_prompt, script = match.groups()
        cuts.append(
            {
                "text": desc.strip(),
                "prompt": image_prompt.strip(),
                "script": script.strip().strip('"“”'),
            }
        )

    if not cuts:
        raise ValueError("GPT 응답에서 컷을 파싱하지 못했습니다. 출력 형식([설명] - [프롬프트] - [스크립트])을 확인해주세요.")

    return cuts, topic_folder
