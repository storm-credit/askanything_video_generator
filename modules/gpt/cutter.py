import os
import json
from typing import Any
from openai import OpenAI
from modules.utils.slugify import slugify_topic

# ✅ 컷 자동 구성 함수 (천만 뷰 쇼츠 기획 전문가 - JSON 구조 도입)
def generate_cuts(topic: str, api_key_override: str = None, lang: str = "ko") -> tuple[list[dict[str, Any]], str]:
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

[Writing Rules: 숏폼 스토리텔링 해부학 (매우 중요)]
당신은 단순히 지식만 나열하는 것이 아니라, 반드시 다음 **[5단계 바이럴 스토리텔링 공식]**에 맞춰 대본을 기획해야 합니다.

1. [Cut 1] Hook (호기심 유발): 3초 만에 시청자의 스크롤을 멈춰야 합니다. 질문에 대한 가장 충격적이거나 궁금증을 유발하는 파격적인 한마디로 시작하세요. (예: "블랙홀에 사람이 빠지면 어떻게 될까요? 결말은 끔찍합니다.")
2. [Cut 2] Context (배경 설명 및 스케일 업): Hook에서 던진 질문에 원리나 배경을 짧게 덧붙여 몰입감을 극대화합니다.
3. [Cut 3~4] Climax (결정적 해답 및 반전): 시청자가 가장 기다려온 '정답'이나 '반전'을 터뜨립니다. 지루한 설명은 빼고 팩트(Fact) 기반의 직관적인 비유로 결과를 명확히 제시하세요. (거짓 정보 절대 금지)
4. [Cut 5] Conclusion & CTA (결론 및 마무리): 결과를 짧게 요약하거나 재치 있는 멘트("구독하고 우주 상식 알아가세요!")로 깔끔하게 떨어지게 마무리합니다.

* 길이 제약: 숏폼은 속도감이 생명입니다. 각 컷 대본은 성우가 3~5초 내에 읽도록 평균 20~30자(최대 50자)로 쳐내어 총 6~10컷으로 구성하세요.

[Expert Validation Check (자가 검증)]
최종 대본을 출력하기 전, 다음 4가지를 스스로 깐깐하게 검증(Self-Correction)하십시오.
1. Hook Test: 첫 대사에 "이게 무슨 소리야?" 하고 스크롤을 멈출 충격적인 반전이나 호기심이 있는가?
2. Pacing Test: 문장에 불필요한 접속사나 부연 설명이 많아 이탈 위험이 있는가? (극단적 요약)
3. Climax Test: 질문에 대한 가장 중요한 해답이 영상 후반부에 카타르시스와 함께 터지는가?
4. Fact Test: 위키피디아 교차 검증 수준의 확실한 과학적/역사적 사실인가?

[Image Engineering Rules: DALL-E 3 시각화]
1. Camera & Lighting: 구도(Extreme Close-up, Wide shot 등)와 조명(Cinematic volumetric lighting, Neon glow 등)을 구체적인 영어로 명시.
2. Consistency: 하이엔드 시네마틱 다큐멘터리 느낌의 초현실주의(Cinematic realism, National Geographic high-end documentary style, hyper-detailed) 퀄리티 유지.
3. Vertical Framing: 'centered composition', 'vertical layout' 명시. 
4. [CRITICAL] Safety Rule: 피, 폭력, 잔인함, 선정성, 특정 상표나 저작권 캐릭터(예: 미키마우스, 스파이더맨), 실존 인물을 절대 프롬프트에 포함하지 마십시오. DALL-E 3 스펙에 맞춰 추상적이고 비유적으로 안전하게(family-friendly) 묘사하세요.

[Output Format Constraint]
반드시 통일된 흐름을 지닌 6~10컷으로 구성하며, 다음 JSON 스키마 구조로만 정확하게 응답하십시오.

{
  "expert_validation": "[대본을 작성하기 전, 당신이 만든 스토리가 Hook, Pacing, Climax, Fact 측면에서 바이럴 숏폼 기준을 만족하는지 스스로 냉정하게 평가한 1~2줄의 커멘트]",
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
    
    final_api_key = api_key_override or os.getenv("OPENAI_API_KEY")
    if not final_api_key:
        raise EnvironmentError("OpenAI API 키가 제공되지 않았습니다. UI에서 입력하거나 .env 파일에 추가하세요.")

    client = OpenAI(api_key=final_api_key)

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
