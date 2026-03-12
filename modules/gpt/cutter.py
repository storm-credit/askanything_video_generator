import os
import json
from typing import Any
from openai import OpenAI
from modules.utils.slugify import slugify_topic
from modules.gpt.search import get_fact_check_context


def _sanitize_cuts(cuts_data: list[dict[str, Any]]) -> list[dict[str, str]]:
    cuts = []
    for cut in cuts_data:
        prompt = cut.get("image_prompt", "").strip()
        script = cut.get("script", "").strip().strip('"“”')
        description = cut.get("description", "").strip()
        if not prompt or not script:
            continue
        cuts.append({"text": description, "prompt": prompt, "script": script})
    return cuts


def _request_cuts(client: OpenAI, model: str, system_prompt: str, user_content: str) -> list[dict[str, str]]:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
    )
    content = (response.choices[0].message.content or "").strip()

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError("GPT 응답이 올바른 JSON 형식이 아닙니다.") from exc

    return _sanitize_cuts(data.get("cuts", []))


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
당신은 단순히 지식만 나열하는 것이 아니라, 반드시 다음 **[5단계 바이럴 스토리텔링 공식]**에 맞춰 6~10컷 분량의 대본을 기획해야 합니다.

1. [Cut 1~2] Hook (호기심 유발): 3초 만에 시청자의 스크롤을 멈춰야 합니다. 질문에 대한 가장 충격적이거나 궁금증을 유발하는 파격적인 한마디로 시작하세요. 
2. [Cut 3] Context (배경 설명 및 스케일 업): Hook에서 던진 질문에 원리나 배경을 짧게 덧붙여 몰입감을 극대화합니다.
3. [Cut 4~5] Build-up (빌드업 및 긴장감 고조): 본격적인 해답을 제시하기 직전, 시청자의 궁금증을 최고조로 끌어올립니다.
4. [Cut 6~8] Climax (결정적 해답 및 반전): 시청자가 가장 기다려온 '정답'이나 '반전'을 터뜨립니다. 팩트 기반의 직관적인 비유로 결과를 명확히 제시하세요.
5. [Cut 9~10 (마지막 1~2컷)] Conclusion & CTA (결론 및 마무리): 결과를 짧게 요약하거나 재치 있는 멘트로 깔끔하게 떨어지게 마무리합니다.

* 길이 제약: 숏폼은 속도감이 생명입니다. 각 컷 대본은 성우가 3~5초 내에 읽도록 20~30자 내외로 자르세요.
* [CRITICAL WARNING] 절대 3~4컷으로 끝내지 말고, 무조건 6~10컷으로 작성하십시오.

[Output Format Constraint]
반드시 통일된 흐름을 지닌 6~10컷 사이로 구성하며, 다음 JSON 스키마 구조로만 정확하게 응답하십시오.

{
  "expert_validation": "[자가 검증 코멘트]",
  "cuts": [
    {
      "description": "[컷 묘사 문장 (한국어)]",
      "image_prompt": "[상세하고 구체적인 DALL-E 3 영어 프롬프트]",
      "script": "[AI 성우가 읽을 한국어 대본]"
    }
  ]
}
"""

    print("-> [기획 전문가] 스크립트 및 기획안 작성 중...")

    # RAG 기법: 실시간 검색 팩트체크 주입
    fact_context = get_fact_check_context(topic)
    user_content = f"주제: '{topic}'에 대한 숏폼 기획안을 작성해주세요."
    if fact_context:
        user_content += f"\n\n{fact_context}"

    model = os.getenv("OPENAI_MODEL", "gpt-4o")

    final_api_key = api_key_override or os.getenv("OPENAI_API_KEY")
    if not final_api_key:
        raise EnvironmentError("OpenAI API 키가 제공되지 않았습니다. UI에서 입력하거나 .env 파일에 추가하세요.")

    client = OpenAI(api_key=final_api_key)

    cuts = _request_cuts(client, model, system_prompt, user_content)

    # 1차 실패 시 재시도 프롬프트 보강
    if not (6 <= len(cuts) <= 10):
        print(f"-> [검증 실패] 컷 수가 {len(cuts)}개입니다. 1회 재요청합니다.")
        retry_user = user_content + "\n\n중요: 이번 응답은 반드시 cuts 배열 길이를 6~10으로 맞추세요."
        cuts = _request_cuts(client, model, system_prompt, retry_user)

    if not (6 <= len(cuts) <= 10):
        raise ValueError(f"컷 수 검증 실패: {len(cuts)}개 생성됨 (요구: 6~10).")

    print(f"OK [기획 전문가] 기획안 완성! ({len(cuts)}컷)")
    return cuts, topic_folder
