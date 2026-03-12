import os
import json
from typing import Any
from openai import OpenAI
from modules.utils.slugify import slugify_topic

# ✅ 컷 자동 구성 함수 (천만 뷰 쇼츠 기획 전문가 - JSON 구조 도입)
def generate_cuts(topic: str, lang: str = "ko") -> tuple[list[dict[str, Any]], str]:
    topic_folder = slugify_topic(topic, lang)

    # ✅ 저장 폴더 구조 생성
    base_path = os.path.join("assets", topic_folder)
    os.makedirs(os.path.join(base_path, "images"), exist_ok=True)
    os.makedirs(os.path.join(base_path, "audio"), exist_ok=True)
    os.makedirs(os.path.join(base_path, "video"), exist_ok=True)

    # ✅ System Prompt (역할 부여 및 엄격한 규칙 강제)
    system_prompt = """
당신은 구독자 100만 명 이상을 보유한 유튜브 쇼츠(Shorts) 및 틱톡(TikTok) 수석 콘텐츠 디렉터이자, 최상급 DALL-E 3 프롬프트 엔지니어입니다.
당신의 임무는 1분 미만의 세로형 숏폼 영상을 위한 완벽한 기획안을 JSON 포맷으로 작성하는 것입니다.

[Writing Rules: 대본 기획]
1. 1초 Hook (최우선): 첫 대사는 시청자의 스크롤 무조건 멈춰야 합니다. 파격적인 질문, 극적인 대비로 시작하세요.
2. Time Constraint (시간 제약, 가장 중요): 숏폼은 속도감이 생명이며 60초를 넘으면 안 됩니다. 각 컷의 대본은 성우가 3~5초 내에 빠르게 읽을 수 있도록 평균 20~30자(최대 50자)로 극단적으로 압축하세요.
3. Pacing & Retention: 지루한 설명은 철저히 배제하고, 직관적인 비유와 반전 장치를 통해 끝까지 시청하도록 유도하세요.

[Image Engineering Rules: DALL-E 3 시각화]
1. Camera & Lighting: 구도(Extreme Close-up, Wide shot 등)와 조명(Cinematic volumetric lighting, Neon glow 등)을 구체적인 영어로 명시.
2. Consistency: 상업용 극장판 3D 애니메이션 퀄리티(Disney Pixar 3D style, Action-packed) 유지.
3. Vertical Framing: 'centered composition', 'vertical layout' 명시. 

[Output Format Constraint]
반드시 통일된 흐름을 지닌 4~6컷으로 구성하며, 다음 JSON 스키마 구조로만 정확하게 응답하십시오.

{
  "cuts": [
    {
      "description": "[컷 묘사 문장 (한국어)]",
      "image_prompt": "[상세하고 구체적인 DALL-E 3 영어 프롬프트]",
      "script": "[AI 성우가 감정을 담아 빠르게 읽을 타격감 있는 한국어 대본]"
    }
  ]
}
"""

    print("-> [기획 전문가] 스크립트 및 기획안 작성 중...")
    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError("환경변수 OPENAI_API_KEY가 설정되어 있지 않습니다.")

    client = OpenAI(api_key=api_key)

    # ✅ JSON Mode 및 System/User 메시지 분리 (프로페셔널 표준)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"주제: '{topic}'에 대한 숏폼 기획안을 작성해주세요."}
        ],
        response_format={ "type": "json_object" }
    )
    print("OK [기획 전문가] 기획안 완성!")

    content = response.choices[0].message.content.strip()

    try:
        data = json.loads(content)
        cuts_data = data.get("cuts", [])
    except json.JSONDecodeError:
        raise ValueError("GPT 응답이 올바른 JSON 형식이 아닙니다.")

    cuts = []
    for cut in cuts_data:
        cuts.append(
            {
                "text": cut.get("description", "").strip(),
                "prompt": cut.get("image_prompt", "").strip(),
                "script": cut.get("script", "").strip().strip('"“”'),
            }
        )

    if not cuts:
        raise ValueError("파싱된 컷 데이터가 없습니다. JSON 출력 형식을 확인해주세요.")

    return cuts, topic_folder
