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
        cuts.append({"text": description, "description": description, "prompt": prompt, "script": script})
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
                  llm_provider: str = "gemini", llm_key_override: str = None,
                  channel: str | None = None) -> tuple[list[dict[str, Any]], str]:
    topic_folder = slugify_topic(topic, lang)

    # 저장 폴더 구조 생성
    base_path = os.path.join("assets", topic_folder)
    os.makedirs(os.path.join(base_path, "images"), exist_ok=True)
    os.makedirs(os.path.join(base_path, "audio"), exist_ok=True)
    os.makedirs(os.path.join(base_path, "video"), exist_ok=True)

    # System Prompt — 언어별 분기
    _SYSTEM_PROMPT_KO = """
당신은 유튜브 쇼츠(Shorts) / 틱톡(TikTok) 바이럴 전문 PD입니다. 조회수 1000만 회 이상을 찍는 자극적이고 중독성 있는 숏폼을 만드는 것이 당신의 유일한 목표입니다.
또한 당신은 최상급 이미지 프롬프트 엔지니어로, 시각적으로 압도적인 장면을 설계합니다.

[바이럴 숏폼 공식 (반드시 준수)]

1. [Cut 1] 결론 폭탄 (Hook): 가장 충격적인 결론/팩트를 첫 문장에 던져라. "~한다고?" "~라는 거 알아?" 식의 구어체 단정문. 질문형 금지. 답을 먼저 때려라.
   나쁜 예: "블랙홀에 빠지면 어떻게 될까요?" → 좋은 예: "블랙홀에 빠지면 몸이 스파게티처럼 늘어난다."
   후크 패턴: 숫자 대비("1000배"), 부정+반전("사실은 반대야"), 시간 긴급성("3년 안에")
2. [Cut 2~3] 충격 확장: "근데 진짜 소름돋는 건..." "더 미친 건 말이야..." 식으로 충격을 연쇄시켜라.
3. [Cut 4~5] 반전 빌드업 + 미니 훅: "근데 여기서 반전이 있어" "사실 이건 시작에 불과해" — 긴장을 최고조로 끌어올려라.
   ★ 중간 이탈 방지: Cut 4에 반드시 새로운 충격 팩트를 던져 "두 번째 훅" 역할을 하게 하라 (리텐션 U자형 곡선 대응).
4. [Cut 6~8] 클라이맥스: 가장 강력한 팩트, 비유, 숫자를 터뜨려라. 직관적인 비유 필수 ("지구 100개를 한 줄로 세운 것과 같아").
5. [Cut 9~10] 여운 + 떡밥: "이거 알고 나면 밤에 잠 못 잘걸?" "다음에 더 소름돋는 거 알려줄게" — 댓글/공유를 유도하는 마무리.

[대본 스타일 규칙]
* 반말 + 구어체. 딱딱한 존댓말 금지. 친구한테 신기한 거 알려주듯이 써라.
* 한 컷 대본은 15~25자. 짧고 강렬하게. 한 문장 이상 넣지 마라.
* "~입니다", "~합니다" 금지. "~거든", "~잖아", "~인 거야", "~라는 거지" 같은 구어체 어미 사용.
* 감탄사/추임새 적극 활용: "미쳤지?", "소름이지?", "진짜야.", "ㄹㅇ."
* 같은 문장 구조를 연속 사용하지 마라. Q&A, 명령문, 서술문을 섞어라.
* [CRITICAL WARNING] 8~10컷으로 작성. 각 컷 약 3.5~5초 (총 30~50초 영상). 절대 5컷 이하 금지.

[이미지 프롬프트 규칙]
* 반드시 영어로 작성. 한국어 금지.
* "vertical 9:16, cinematic, no text" 필수 포함.
* 매 컷마다 카메라 앵글/조명을 다르게 설정 (단조로움 방지).
* 사람 얼굴 정면 클로즈업 금지 (AI 생성 얼굴은 언캐니밸리).
* 구체적 시각 디테일 포함: 색온도, 재질감, 스케일 비교 (예: "car-sized asteroid").

[컷별 감정 태그 — 카메라/페이싱 연동용]
각 컷의 description 끝에 감정 태그를 추가하라:
  [SHOCK] = 충격/공포 → 빠른 줌
  [WONDER] = 경이/감탄 → 부드러운 패닝
  [TENSION] = 긴장/빌드업 → 느린 접근
  [REVEAL] = 반전/폭로 → 급격한 전환
  [CALM] = 여운/마무리 → 정적
예시: "거대한 블랙홀이 빛을 삼키는 장면 [SHOCK]"

[골든 예시 — 주제: "태양이 사라지면 생기는 일" (대표 3컷만 표시, 실제로는 8~10컷 작성)]
{
  "title": "태양이 사라지면 생기는 일",
  "expert_validation": "NASA 공식 데이터 기반, 물리학 법칙 검증 완료",
  "cuts": [
    {"description": "완전한 어둠 속 지구 전경, 태양 자리에 검은 void [SHOCK]", "image_prompt": "Earth floating in complete darkness, where the sun used to be is now an empty black void, deep space, dramatic volumetric lighting from distant stars only, vertical 9:16, cinematic, no text", "script": "태양이 갑자기 사라지면 8분 동안 아무도 모른다고."},
    {"description": "중력 해방된 행성들이 흩어지는 태양계 [WONDER]", "image_prompt": "Solar system planets scattering in different directions without gravitational center, beautiful chaos of planetary bodies drifting apart, cosmic scale, vertical 9:16, cinematic, no text", "script": "태양 중력이 사라지면 행성 전부 흩어져버리거든."},
    {"description": "시청자를 향한 클로즈업 느낌의 우주 배경 [CALM]", "image_prompt": "Dramatic close perspective looking up at vast dark cosmos filled with distant galaxies, sense of insignificance and wonder, immersive vertical composition 9:16, cinematic, no text", "script": "이거 알고 나면 밤하늘 다르게 보일걸?"}
  ]
}

[JSON 출력 필수]
- 마크다운 코드블록 없이 순수 JSON만 출력
- 첫 문자: {  마지막 문자: }

[Output Format]
8~10컷, 다음 JSON만 출력:

{
  "title": "[자극적이고 클릭을 부르는 한국어 제목 (15자 이내, ~하면 생기는 일, ~의 비밀 등)]",
  "expert_validation": "[자가 검증]",
  "cuts": [
    {
      "description": "[컷 묘사 (한국어)] [감정태그]",
      "image_prompt": "[DALL-E 3 영어 프롬프트: 세로 9:16, 시네마틱, 극적 조명, 텍스트 없이]",
      "script": "[성우 대본: 구어체 반말, 15~25자]"
    }
  ]
}
"""

    _SYSTEM_PROMPT_EN = """
You are a viral YouTube Shorts / TikTok producer. Your ONLY goal is creating addictive, scroll-stopping short-form content that gets 10M+ views.
You are also a top-tier image prompt engineer who designs visually overwhelming scenes.

[Viral Short-form Formula (MUST FOLLOW)]

1. [Cut 1] Conclusion Bomb (Hook): Drop the most shocking fact/conclusion in the FIRST sentence. Use declarative statements, NOT questions. Lead with the answer.
   BAD: "What happens if you fall into a black hole?" → GOOD: "If you fall into a black hole, your body stretches like spaghetti."
   Hook patterns: Numerical contrast ("1000x more"), Negation+reveal ("It's actually the opposite"), Time urgency ("Within 3 years")
2. [Cut 2–3] Shock Chain: "But here's the insane part..." "What's even crazier is..." — chain the shock.
3. [Cut 4–5] Twist Build-up + Mini Hook: "But here's the plot twist" "And this is just the beginning" — maximize tension.
   ★ Mid-video retention: Cut 4 MUST introduce a brand-new shocking fact as a "second hook" (counters U-shaped retention drop).
4. [Cut 6–8] Climax: Drop the hardest facts, analogies, numbers. Use intuitive comparisons ("That's like lining up 100 Earths").
5. [Cut 9–10] Cliffhanger + Bait: "You won't sleep tonight after knowing this" "I'll tell you something even crazier next time" — drive comments/shares.

[Script Style Rules]
* Casual, conversational tone. Talk like you're telling a friend something mind-blowing.
* Each cut: 5–10 words MAX. Short. Punchy. One sentence only.
* Use exclamations: "Insane, right?", "No way.", "Dead serious.", "Think about that."
* Never repeat the same sentence structure in consecutive cuts. Mix Q&A, imperative, declarative.
* [CRITICAL WARNING] Write 8–10 cuts (~3.5–5 sec each). 30–50 second video. NEVER less than 5 cuts.

[Image Prompt Rules]
* ALL image prompts must be in English.
* MUST include "vertical 9:16, cinematic, no text" in every prompt.
* Vary camera angle and lighting per cut (avoid visual monotony).
* NO frontal close-ups of human faces (AI-generated faces trigger uncanny valley).
* Include specific visual details: color temperature, material textures, scale comparisons (e.g. "car-sized asteroid").

[Emotion Tags — for camera/pacing sync]
Add an emotion tag at the END of each description:
  [SHOCK] = shock/horror → aggressive zoom
  [WONDER] = awe/amazement → gentle pan
  [TENSION] = suspense/build-up → slow approach
  [REVEAL] = twist/revelation → sudden shift
  [CALM] = reflection/outro → static
Example: "A massive black hole swallowing light [SHOCK]"

[Golden Example — Topic: "What happens if the sun disappears" (3 representative cuts shown, write 8–10 in practice)]
{
  "title": "The Sun Vanishes Tomorrow",
  "expert_validation": "Based on NASA data and verified physics",
  "cuts": [
    {"description": "Earth in complete darkness, empty void where sun was [SHOCK]", "image_prompt": "Earth floating in complete darkness, where the sun used to be is now an empty black void, deep space, dramatic volumetric lighting from distant stars only, vertical 9:16, cinematic, no text", "script": "The sun vanishes and nobody knows for 8 minutes."},
    {"description": "Planets scattering without gravitational center [WONDER]", "image_prompt": "Solar system planets scattering in all directions, beautiful chaos of planetary bodies, cosmic scale, vertical 9:16, cinematic, no text", "script": "No sun gravity means every planet drifts apart."},
    {"description": "Vast cosmos perspective looking up [CALM]", "image_prompt": "Dramatic close perspective looking up at vast dark cosmos, distant galaxies, sense of wonder, vertical 9:16, cinematic, no text", "script": "You'll never look at the night sky the same."}
  ]
}

[JSON Output Required]
- Output pure JSON only, no markdown code blocks
- First character: {  Last character: }

[Output Format]
8–10 cuts, output ONLY this JSON:

{
  "title": "[Click-bait English title (max 8 words)]",
  "expert_validation": "[Self-validation]",
  "cuts": [
    {
      "description": "[Cut description (English)] [EMOTION_TAG]",
      "image_prompt": "[DALL-E 3 English prompt: vertical 9:16, cinematic, dramatic lighting, no text]",
      "script": "[Voice-over: casual, 5-10 words]"
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

    # 채널별 비주얼 스타일 주입 (이미지 프롬프트 차별화 — 유튜브 스팸 회피)
    if channel:
        from modules.utils.channel_config import get_channel_preset
        preset = get_channel_preset(channel)
        if preset:
            visual_style = preset.get("visual_style", "")
            tone = preset.get("tone", "")
            if visual_style:
                system_prompt += f"""

[CHANNEL VISUAL IDENTITY]
All "image_prompt" fields MUST follow this visual style: {visual_style}
This is the channel's signature look — every image should feel cohesive with this aesthetic.
"""
            if tone and lang != "ko" and lang != "en":
                # 기타 언어용: 톤도 주입
                system_prompt += f"\nNarrator tone: {tone}\n"

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
        max_key_attempts = 3  # OpenAI/Claude도 429 시 최대 3회 재시도 (백오프)

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
            elif is_retryable:
                # OpenAI/Claude 429: 지수 백오프 후 재시도
                import time as _time, random as _random
                wait = min(2 ** (attempt + 1), 30) + _random.uniform(0, 2)
                print(f"  [{provider_label} 429] {wait:.1f}초 후 재시도... ({attempt+1}/{max_key_attempts})")
                _time.sleep(wait)
                continue
            else:
                raise  # 429가 아닌 에러는 그대로 전파

    # 컷 수 검증 — 초과 시 트림, 부족 시 기존 컷 기반 확장 요청 (전체 재생성 방지)
    if len(cuts) > 10:
        print(f"-> [검증] 컷 수 {len(cuts)}개 → 10개로 트림")
        cuts = cuts[:10]
    elif len(cuts) < 6:
        print(f"-> [검증 실패] 컷 수가 {len(cuts)}개입니다. 기존 컷 기반 확장 요청합니다 (목표: 8~10컷).")
        if llm_provider == "gemini":
            retry_key = get_google_key(None, service="gemini", exclude=exhausted_keys) or current_key
        else:
            retry_key = current_key
        # 기존 컷 데이터를 포함하여 확장만 요청 (전체 재생성 대신)
        existing_cuts_json = json.dumps([{"script": c["script"], "description": c.get("text", "")} for c in cuts], ensure_ascii=False)
        retry_user = (
            user_content
            + f"\n\n기존에 {len(cuts)}컷이 생성되었습니다. 아래 기존 컷 사이에 중간 컷을 추가하여 총 8~10컷으로 확장하세요. "
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

    if len(cuts) > 10:
        cuts = cuts[:10]
    if len(cuts) < 6:
        raise ValueError(f"컷 수 검증 실패: {len(cuts)}개 생성됨 (요구: 6~10).")

    # title이 비어있으면 topic을 폴백으로 사용
    if not title:
        title = topic

    print(f"OK [기획 전문가] 기획안 완성! ({len(cuts)}컷, {provider_label}) 제목: {title}")
    return cuts, topic_folder, title
