import os
import json
import re
from typing import Any
from modules.utils.slugify import slugify_topic
from modules.utils.constants import PROVIDER_LABELS
from modules.gpt.search import get_fact_check_context


def _sanitize_cuts(cuts_data: list[dict[str, Any]]) -> list[dict[str, str]]:
    cuts = []
    for cut in cuts_data:
        prompt = cut.get("image_prompt", "").strip()
        script = cut.get("script", "").strip().strip('"""')
        description = cut.get("description", "").strip()
        if not prompt or not script:
            continue
        cuts.append({"text": description, "prompt": prompt, "script": script})
    return cuts


def _extract_json(text: str) -> dict:
    """LLM 응답에서 JSON을 추출합니다. 마크다운 코드블록 래핑도 처리."""
    text = text.strip()
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


def _parse_cuts(content: str) -> tuple[list[dict[str, str]], str]:
    """LLM 응답 텍스트에서 cuts 데이터와 제목을 파싱합니다."""
    if not content:
        raise ValueError("LLM 응답 content가 비어 있습니다.")
    try:
        data = _extract_json(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM 응답이 올바른 JSON 형식이 아닙니다: {content[:200]}") from exc
    cuts = _sanitize_cuts(data.get("cuts", []))
    if not cuts:
        raise ValueError("LLM 응답에 유효한 cuts가 없습니다.")
    title = data.get("title", "").strip()
    return cuts, title


def _request_openai(api_key: str, system_prompt: str, user_content: str) -> str | None:
    """OpenAI GPT API로 기획안을 생성합니다."""
    from openai import OpenAI
    model = os.getenv("OPENAI_MODEL", "gpt-4o")
    client = OpenAI(api_key=api_key, timeout=120)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
    )
    if not response.choices:
        raise ValueError("OpenAI 응답에 choices가 비어 있습니다.")
    return (response.choices[0].message.content or "").strip()


def _request_gemini(api_key: str, system_prompt: str, user_content: str) -> str:
    """Google Gemini API로 기획안을 생성합니다 (google-genai SDK)."""
    from google import genai
    from google.genai import types
    model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model_name,
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            http_options=types.HttpOptions(timeout=120_000),
        ),
    )
    return (response.text or "").strip()


def _request_claude(api_key: str, system_prompt: str, user_content: str) -> str:
    """Anthropic Claude API로 기획안을 생성합니다."""
    import anthropic
    model_name = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
    client = anthropic.Anthropic(api_key=api_key, timeout=120)
    json_instruction = "\n\n[CRITICAL] 반드시 순수 JSON만 출력하세요. 마크다운 코드블록이나 설명 텍스트 없이 JSON 객체만 반환하십시오."
    response = client.messages.create(
        model=model_name,
        max_tokens=4096,
        system=system_prompt + json_instruction,
        messages=[{"role": "user", "content": user_content}],
    )
    if not response.content:
        raise ValueError("Claude 응답에 content가 비어 있습니다.")
    return (response.content[0].text or "").strip()


def _request_cuts(provider: str, api_key: str, system_prompt: str, user_content: str) -> tuple[list[dict[str, str]], str]:
    """지정된 LLM 프로바이더로 컷 데이터를 요청하고 파싱합니다. (cuts, title) 반환."""
    if provider == "gemini":
        content = _request_gemini(api_key, system_prompt, user_content)
    elif provider == "claude":
        content = _request_claude(api_key, system_prompt, user_content)
    else:
        content = _request_openai(api_key, system_prompt, user_content)
    return _parse_cuts(content)


# 컷 자동 구성 함수 (천만 뷰 쇼츠 기획 전문가 - 멀티 LLM 지원)
def generate_cuts(topic: str, api_key_override: str = None, lang: str = "ko",
                  llm_provider: str = "gemini", llm_key_override: str = None) -> tuple[list[dict[str, Any]], str]:
    topic_folder = slugify_topic(topic, lang)

    # 저장 폴더 구조 생성
    base_path = os.path.join("assets", topic_folder)
    os.makedirs(os.path.join(base_path, "images"), exist_ok=True)
    os.makedirs(os.path.join(base_path, "audio"), exist_ok=True)
    os.makedirs(os.path.join(base_path, "video"), exist_ok=True)

    # System Prompt — 언어별 분기
    _SYSTEM_PROMPT_KO = """
당신은 구독자 100만 명 이상을 보유한 유튜브 쇼츠(Shorts) 및 틱톡(TikTok) 수석 콘텐츠 디렉터이자, 최상급 DALL-E 3 프롬프트 엔지니어입니다.
당신의 임무는 1분 미만의 세로형 숏폼 영상을 위한 완벽한 기획안을 JSON 포맷으로 작성하는 것입니다.

[Writing Rules: 숏폼 스토리텔링 해부학 (매우 중요)]
당신은 단순히 지식만 나열하는 것이 아니라, 반드시 다음 **[5단계 바이럴 스토리텔링 공식]**에 맞춰 8~15컷 분량의 대본을 기획해야 합니다.

1. [Cut 1~2] Hook (호기심 유발): 3초 만에 시청자의 스크롤을 멈춰야 합니다. 질문에 대한 가장 충격적이거나 궁금증을 유발하는 파격적인 한마디로 시작하세요.
2. [Cut 3~4] Context (배경 설명 및 스케일 업): Hook에서 던진 질문에 원리나 배경을 짧게 덧붙여 몰입감을 극대화합니다.
3. [Cut 5~7] Build-up (빌드업 및 긴장감 고조): 본격적인 해답을 제시하기 직전, 시청자의 궁금증을 최고조로 끌어올립니다.
4. [Cut 8~12] Climax (결정적 해답 및 반전): 시청자가 가장 기다려온 '정답'이나 '반전'을 터뜨립니다. 팩트 기반의 직관적인 비유로 결과를 명확히 제시하세요.
5. [Cut 13~15 (마지막 1~3컷)] Conclusion & CTA (결론 및 마무리): 결과를 짧게 요약하거나 재치 있는 멘트로 깔끔하게 떨어지게 마무리합니다.

* 길이 제약: 숏폼은 속도감이 생명입니다. 각 컷 대본은 성우가 3~5초 내에 읽도록 20~30자 내외로 자르세요.
* [CRITICAL WARNING] 절대 7컷 이하로 끝내지 말고, 무조건 8~15컷으로 작성하십시오. 최소 30초 이상의 영상이 되어야 합니다.

[Output Format Constraint]
반드시 통일된 흐름을 지닌 8~15컷 사이로 구성하며, 다음 JSON 스키마 구조로만 정확하게 응답하십시오.

{
  "title": "[영상 제목: 시청자의 클릭을 유도하는 짧고 임팩트 있는 한국어 제목 (15자 이내)]",
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

    _SYSTEM_PROMPT_EN = """
You are a senior content director for YouTube Shorts and TikTok with over 1 million subscribers, and a top-tier DALL-E 3 prompt engineer.
Your mission is to create a perfect production plan in JSON format for a vertical short-form video under 1 minute.

[Writing Rules: Short-form Storytelling Anatomy (VERY IMPORTANT)]
You must follow this **[5-Step Viral Storytelling Formula]** to plan an 8–15 cut script:

1. [Cut 1–2] Hook: Stop the viewer's scroll within 3 seconds. Open with the most shocking or curiosity-provoking statement about the topic.
2. [Cut 3–4] Context: Briefly add background or principles to deepen immersion.
3. [Cut 5–7] Build-up: Maximize curiosity right before revealing the answer.
4. [Cut 8–12] Climax: Deliver the key answer or twist. Use fact-based, intuitive analogies.
5. [Cut 13–15 (last 1–3 cuts)] Conclusion & CTA: Summarize the result or end with a witty closing remark.

* Length constraint: Speed is the soul of short-form. Each cut script should be 5–10 words, readable by a voice actor in 3–5 seconds.
* [CRITICAL WARNING] NEVER end with only 7 or fewer cuts. You MUST write 8–15 cuts. The video must be at least 30 seconds long.

[Output Format Constraint]
Compose exactly 8–15 cuts with a unified narrative flow, and respond ONLY in the following JSON schema:

{
  "title": "[Video title: A short, impactful, click-worthy English title (max 8 words)]",
  "expert_validation": "[Self-validation comment]",
  "cuts": [
    {
      "description": "[Cut description sentence (English)]",
      "image_prompt": "[Detailed DALL-E 3 English prompt]",
      "script": "[English voice-over script for AI narrator]"
    }
  ]
}
"""

    # 언어별 프롬프트 매핑
    _LANG_NAMES = {
        "ko": "Korean", "en": "English", "de": "German", "da": "Danish",
        "no": "Norwegian", "es": "Spanish", "fr": "French", "pt": "Portuguese",
        "it": "Italian", "nl": "Dutch", "sv": "Swedish", "pl": "Polish",
        "ru": "Russian", "ja": "Japanese", "zh": "Chinese", "ar": "Arabic",
        "tr": "Turkish", "hi": "Hindi",
    }
    if lang == "ko":
        system_prompt = _SYSTEM_PROMPT_KO
    elif lang == "en":
        system_prompt = _SYSTEM_PROMPT_EN
    else:
        # 기타 언어: 영어 프롬프트 기반 + 해당 언어로 대본/제목 작성 지시
        lang_name = _LANG_NAMES.get(lang, lang)
        system_prompt = _SYSTEM_PROMPT_EN + f"""

[LANGUAGE OVERRIDE]
You MUST write ALL "script" fields and the "title" field in {lang_name}.
The "image_prompt" and "description" fields must remain in English.
The narrator will speak in {lang_name}, so the script must be natural {lang_name}.
"""

    # LLM 프로바이더별 API 키 결정
    provider_label = PROVIDER_LABELS.get(llm_provider, "ChatGPT")

    if llm_provider == "gemini":
        final_api_key = llm_key_override or os.getenv("GEMINI_API_KEY")
        if not final_api_key:
            raise EnvironmentError("Gemini API 키가 제공되지 않았습니다. .env에 GEMINI_API_KEY를 설정하세요.")
    elif llm_provider == "claude":
        final_api_key = llm_key_override or os.getenv("ANTHROPIC_API_KEY")
        if not final_api_key:
            raise EnvironmentError("Claude API 키가 제공되지 않았습니다. .env에 ANTHROPIC_API_KEY를 설정하세요.")
    else:
        final_api_key = api_key_override or os.getenv("OPENAI_API_KEY")
        if not final_api_key:
            raise EnvironmentError("OpenAI API 키가 제공되지 않았습니다. .env에 OPENAI_API_KEY를 설정하세요.")

    print(f"-> [기획 전문가] {provider_label} 기반 스크립트 및 기획안 작성 중...")

    # RAG 기법: 실시간 검색 팩트체크 주입
    fact_context = get_fact_check_context(topic)
    if lang == "en":
        user_content = f"Topic: Create a short-form video plan about '{topic}'."
    else:
        user_content = f"주제: '{topic}'에 대한 숏폼 기획안을 작성해주세요."
    if fact_context:
        user_content += f"\n\n{fact_context}"

    # 429 자동 키 전환: 실패한 키를 차단하고 다른 키로 재시도
    exhausted_keys: set[str] = set()
    current_key = final_api_key
    cuts: list[dict[str, str]] = []
    title: str = ""

    if llm_provider == "gemini":
        from modules.utils.keys import get_google_key, mark_key_exhausted, mask_key
        max_key_attempts = 10  # 최대 키 전환 횟수
    else:
        max_key_attempts = 1  # Gemini 외 프로바이더는 단일 키

    for attempt in range(max_key_attempts):
        try:
            cuts, title = _request_cuts(llm_provider, current_key, system_prompt, user_content)
            break  # 성공
        except Exception as e:
            err_str = str(e)
            is_retryable = (
                "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                or "503" in err_str or "UNAVAILABLE" in err_str
                or "quota" in err_str.lower() or "rate_limit" in err_str.lower()
            )

            if is_retryable and llm_provider == "gemini":
                mark_key_exhausted(current_key, service="gemini")
                exhausted_keys.add(current_key)
                next_key = get_google_key(None, service="gemini", exclude=exhausted_keys)

                if next_key and next_key not in exhausted_keys:
                    print(f"  [키 전환] {mask_key(current_key)} → {mask_key(next_key)} (gemini 429 자동 전환)")
                    current_key = next_key
                    continue
                else:
                    raise RuntimeError(f"[Gemini 할당량 초과] 등록된 모든 키({len(exhausted_keys)}개)의 쿼터가 소진되었습니다.") from e
            else:
                raise  # 429가 아닌 에러는 그대로 전파

    # 컷 수 검증 — 초과 시 트림, 부족 시 기존 컷 기반 확장 요청 (전체 재생성 방지)
    if len(cuts) > 15:
        print(f"-> [검증] 컷 수 {len(cuts)}개 → 15개로 트림")
        cuts = cuts[:15]
    elif len(cuts) < 8:
        print(f"-> [검증 실패] 컷 수가 {len(cuts)}개입니다. 기존 컷 기반 확장 요청합니다.")
        if llm_provider == "gemini":
            retry_key = get_google_key(None, service="gemini", exclude=exhausted_keys) or current_key
        else:
            retry_key = current_key
        # 기존 컷 데이터를 포함하여 확장만 요청 (전체 재생성 대신)
        existing_cuts_json = json.dumps([{"script": c["script"], "description": c.get("text", "")} for c in cuts], ensure_ascii=False)
        retry_user = (
            user_content
            + f"\n\n기존에 {len(cuts)}컷이 생성되었습니다. 아래 기존 컷 사이에 중간 컷을 추가하여 총 10~12컷으로 확장하세요. "
            + f"기존 컷의 흐름과 스타일을 유지하면서 빌드업/클라이맥스 구간을 보강하세요.\n기존 컷: {existing_cuts_json}"
        )
        try:
            cuts, title = _request_cuts(llm_provider, retry_key, system_prompt, retry_user)
        except Exception as retry_err:
            err_str = str(retry_err)
            if llm_provider == "gemini" and ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str):
                mark_key_exhausted(retry_key, service="gemini")
                print(f"  [컷 수 재시도 429] {mask_key(retry_key)} 차단됨 — 기존 {len(cuts)}컷으로 진행")
            else:
                raise

    if len(cuts) > 15:
        cuts = cuts[:15]
    if len(cuts) < 8:
        raise ValueError(f"컷 수 검증 실패: {len(cuts)}개 생성됨 (요구: 8~15).")

    # title이 비어있으면 topic을 폴백으로 사용
    if not title:
        title = topic

    print(f"OK [기획 전문가] 기획안 완성! ({len(cuts)}컷, {provider_label}) 제목: {title}")
    return cuts, topic_folder, title
