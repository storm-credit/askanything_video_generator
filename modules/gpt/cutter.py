import os
import json
import re
import time
import random
import hashlib
import threading
from typing import Any
from modules.utils.slugify import slugify_topic
from modules.utils.constants import PROVIDER_LABELS
from modules.gpt.search import get_fact_check_context

_YT_CONTENT_SEP = "\n\n[원본 영상 내용]\n"

def _split_yt_topic(topic: str) -> tuple[str, str]:
    """YouTube 자막이 포함된 topic을 (제목, 자막내용)으로 분리. 자막 없으면 ('', '')."""
    if _YT_CONTENT_SEP in topic:
        title, content = topic.split(_YT_CONTENT_SEP, 1)
        return title.strip(), content.strip()
    # 구분자 없이 [원본 영상 내용]만 있는 경우 (trailing newline 없음)
    marker = "\n\n[원본 영상 내용]"
    if marker in topic:
        title = topic.split(marker, 1)[0].strip()
        return title, ""
    return topic, ""


def _sanitize_cuts(cuts_data: list[dict[str, Any]]) -> list[dict[str, str]]:
    cuts = []
    for cut in cuts_data:
        prompt = cut.get("image_prompt", "").strip()
        script = cut.get("script", "").strip().strip('"""')
        description = cut.get("description", "").strip()
        if not prompt or not script:
            print(f"  [경고] 빈 컷 제거됨: prompt={bool(prompt)}, script={bool(script)}, desc='{description[:30]}'")
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


def _parse_cuts(content: str) -> tuple[list[dict[str, str]], str, list[str]]:
    """LLM 응답 텍스트에서 cuts 데이터, 제목, 태그를 파싱합니다."""
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
    tags = data.get("tags", ["#Shorts"])
    return cuts, title, tags


_CUTS_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "video_cuts",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                },
                "cuts": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "description": {"type": "string"},
                            "image_prompt": {"type": "string"},
                            "script": {"type": "string"},
                        },
                        "required": ["description", "image_prompt", "script"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["title", "tags", "cuts"],
            "additionalProperties": False,
        },
    },
}

_GEMINI_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "title": {"type": "STRING"},
        "tags": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
        },
        "cuts": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "description": {"type": "STRING"},
                    "image_prompt": {"type": "STRING"},
                    "script": {"type": "STRING"},
                },
                "required": ["description", "image_prompt", "script"],
            },
        },
    },
    "required": ["title", "tags", "cuts"],
}


def _request_openai(api_key: str, system_prompt: str, user_content: str, model_override: str | None = None) -> str | None:
    """OpenAI GPT API로 기획안을 생성합니다."""
    from openai import OpenAI
    model = model_override or os.getenv("OPENAI_MODEL", "gpt-4o")
    client = OpenAI(api_key=api_key, timeout=120)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        response_format=_CUTS_JSON_SCHEMA,
        temperature=0.75,
    )
    if not response.choices:
        raise ValueError("OpenAI 응답에 choices가 비어 있습니다.")
    return (response.choices[0].message.content or "").strip()


_gemini_cache: dict[str, object] = {}  # key → cached_content (최대 20개, 초과 시 가장 오래된 것 제거)
_gemini_cache_lock = threading.Lock()
_GEMINI_CACHE_MAX = 20

def _request_gemini(api_key: str, system_prompt: str, user_content: str, model_override: str | None = None) -> str:
    """Google Gemini API로 기획안을 생성합니다 (google-genai SDK). 시스템 프롬프트 캐싱 지원."""
    from google import genai
    from google.genai import types
    model_name = model_override or os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
    client = genai.Client(api_key=api_key)

    # Context Caching: 시스템 프롬프트를 캐시하여 토큰 비용 절감
    # 캐시 키에 프롬프트 해시 포함 (lang/channel 변경 시 잘못된 캐시 사용 방지)
    prompt_hash = hashlib.sha256(system_prompt.encode()).hexdigest()[:12]
    cache_key = f"{api_key}:{model_name}:{prompt_hash}"
    with _gemini_cache_lock:
        cached = _gemini_cache.get(cache_key)
    try:
        if cached:
            # 캐시된 컨텍스트 사용
            response = client.models.generate_content(
                model=model_name,
                contents=user_content,
                config=types.GenerateContentConfig(
                    cached_content=cached,
                    response_mime_type="application/json",
                    response_schema=_GEMINI_RESPONSE_SCHEMA,
                    temperature=0.75,
                    http_options=types.HttpOptions(timeout=120_000),
                ),
            )
            return (response.text or "").strip()
    except Exception:
        # 캐시 만료 등 실패 시 일반 요청으로 폴백
        with _gemini_cache_lock:
            _gemini_cache.pop(cache_key, None)

    # 캐시 생성 시도 (실패해도 일반 요청으로 진행)
    try:
        cached = client.caches.create(
            model=model_name,
            config=types.CreateCachedContentConfig(
                system_instruction=system_prompt,
                ttl="3600s",
            ),
        )
        # 캐시 크기 제한 (LRU 간이 구현: 초과 시 첫 번째 키 제거)
        with _gemini_cache_lock:
            if len(_gemini_cache) >= _GEMINI_CACHE_MAX:
                oldest_key = next(iter(_gemini_cache))
                _gemini_cache.pop(oldest_key, None)
            _gemini_cache[cache_key] = cached.name
        response = client.models.generate_content(
            model=model_name,
            contents=user_content,
            config=types.GenerateContentConfig(
                cached_content=cached.name,
                response_mime_type="application/json",
                response_schema=_GEMINI_RESPONSE_SCHEMA,
                temperature=0.75,
                http_options=types.HttpOptions(timeout=120_000),
            ),
        )
    except Exception:
        # 캐시 미지원 모델이거나 에러 → 일반 요청
        response = client.models.generate_content(
            model=model_name,
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                response_schema=_GEMINI_RESPONSE_SCHEMA,
                temperature=0.75,
                http_options=types.HttpOptions(timeout=120_000),
            ),
        )
    return (response.text or "").strip()


def _request_claude(api_key: str, system_prompt: str, user_content: str, model_override: str | None = None) -> str:
    """Anthropic Claude API로 기획안을 생성합니다."""
    import anthropic
    model_name = model_override or os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
    client = anthropic.Anthropic(api_key=api_key, timeout=120)
    json_instruction = "\n\n[CRITICAL JSON OUTPUT] You MUST output ONLY valid JSON. No markdown code blocks, no explanation text. Return a raw JSON object only."
    response = client.messages.create(
        model=model_name,
        max_tokens=4096,
        temperature=0.75,
        system=system_prompt + json_instruction,
        messages=[{"role": "user", "content": user_content}],
    )
    if not response.content:
        raise ValueError("Claude 응답에 content가 비어 있습니다.")
    return (response.content[0].text or "").strip()


def _request_cuts(provider: str, api_key: str, system_prompt: str, user_content: str, model_override: str | None = None) -> tuple[list[dict[str, str]], str, list[str]]:
    """지정된 LLM 프로바이더로 컷 데이터를 요청하고 파싱합니다. (cuts, title, tags) 반환."""
    if provider == "gemini":
        content = _request_gemini(api_key, system_prompt, user_content, model_override)
    elif provider == "claude":
        content = _request_claude(api_key, system_prompt, user_content, model_override)
    else:
        content = _request_openai(api_key, system_prompt, user_content, model_override)
    return _parse_cuts(content)


# 컷 자동 구성 함수 (천만 뷰 쇼츠 기획 전문가 - 멀티 LLM 지원)
def generate_cuts(topic: str, api_key_override: str = None, lang: str = "ko",
                  llm_provider: str = "gemini", llm_key_override: str = None,
                  channel: str | None = None, llm_model: str | None = None,
                  reference_url: str | None = None) -> tuple[list[dict[str, Any]], str, str, list[str]]:
    # YouTube 자막 포함된 topic에서 제목/자막 분리
    _topic_title, _topic_content = _split_yt_topic(topic)
    if not _topic_title:
        _topic_title = topic
    topic_folder = slugify_topic(_topic_title, lang)

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
   ★ [1.7초 법칙] 시청자의 71%가 1.7초 내에 이탈을 결정한다. Cut 1의 image_prompt는 반드시 시각적 충격이 있어야 한다 (극단적 스케일, 강렬한 색상 대비, 비현실적 장면).
   나쁜 예: "블랙홀에 빠지면 어떻게 될까요?" → 좋은 예: "블랙홀에 빠지면 몸이 스파게티처럼 늘어난다."
   후크 패턴: 숫자 대비("1000배"), 부정+반전("사실은 반대야"), 시간 긴급성("3년 안에"), 직관 파괴("상식이 틀렸어")
2. [Cut 2~3] 충격 확장: "근데 진짜 소름돋는 건..." "더 미친 건 말이야..." 식으로 충격을 연쇄시켜라.
3. [Cut 4~5] 반전 빌드업 + 미니 훅: "근데 여기서 반전이 있어" "사실 이건 시작에 불과해" — 긴장을 최고조로 끌어올려라.
   ★ 중간 이탈 방지: Cut 4에 반드시 새로운 충격 팩트를 던져 "두 번째 훅" 역할을 하게 하라 (리텐션 U자형 곡선 대응).
   ★ [패턴 인터럽트] 매 2~3컷마다 카메라 앵글/조명/스케일을 급격히 바꿔라. 단조로운 시각은 이탈률 85% 증가 원인.
4. [Cut 6~8] 클라이맥스: 가장 강력한 팩트, 비유, 숫자를 터뜨려라. 직관적인 비유 필수 ("지구 100개를 한 줄로 세운 것과 같아").
5. [Cut 9~10] 의문 해소 + 여운: Cut 1에서 던진 훅/충격 팩트를 마지막에 반드시 회수하라. 시청자가 "아 그래서 그랬구나"라고 납득하게 만들어라.
   ★ [마무리 필수 규칙]
   - 마지막 컷은 훅에서 제기한 의문/주장에 대한 결론적 답변이어야 한다.
   - 의문문("~걸?", "~일까?")으로 끝내지 마라. 답을 주고 끝내라.
   - 단, 딱딱한 서술형("~이다", "~한다") 금지. 대화체("~거든", "~인 거야", "~라는 거지")로 마무리.
   - "다음엔 알려줄게", "구독하면 알려줄게" 같은 빈 약속형 CTA 절대 금지. 시청자 이탈 원인.
   - 마지막 컷은 강렬한 여운으로 끝내라: 충격 반전, 감정적 울림, 또는 새로운 관점 제시.
   좋은 예: Cut1 "블랙홀에 빠지면 스파게티가 돼" → 마지막 "근데 진짜 무서운 건, 네가 그걸 느끼면서 죽는다는 거야."
   좋은 예: "그래서 우주가 무섭냐고? 아니. 우리가 여기 있다는 게 기적인 거야."
   나쁜 예: "다음엔 더 소름돋는 거 알려줄게" (약속 불이행, 신뢰 하락)
   나쁜 예: "이거 알고 나면 밤하늘이 다르게 보일걸?" (의문만 던지고 답 없음)

[대본 스타일 규칙]
* 반말 + 구어체. 딱딱한 존댓말 금지. 친구한테 신기한 거 알려주듯이 써라.
* 한 컷 대본은 15~30자. 짧고 강렬하게. 한 문장 이상 넣지 마라.
* "~입니다", "~합니다" 금지. "~거든", "~잖아", "~인 거야", "~라는 거지" 같은 구어체 어미 사용.
* 감탄사/추임새 적극 활용: "미쳤지?", "소름이지?", "진짜야.", "ㄹㅇ."
* 같은 문장 구조를 연속 사용하지 마라. Q&A, 명령문, 서술문을 섞어라.
* [CRITICAL WARNING] 7~10컷으로 작성. 각 컷 약 5~7초 (총 50~60초 영상 목표 — 시청시간 극대화). 절대 7컷 미만 금지.

[이미지 프롬프트 규칙]
* 반드시 영어로 작성. 한국어 금지.
* 시스템이 자동으로 "vertical 9:16, cinematic, no text" 스타일을 이미지 프롬프트 앞에 추가하므로 직접 쓰지 마라.
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

[골든 예시 — 주제: "태양이 사라지면 생기는 일" (대표 3컷만 표시, 실제로는 7~10컷 작성)]
{
  "title": "태양이 사라지면 생기는 일",
  "cuts": [
    {"description": "완전한 어둠 속 지구 전경, 태양 자리에 검은 void [SHOCK]", "image_prompt": "Earth floating in complete darkness, where the sun used to be is now an empty black void, deep space, dramatic volumetric lighting from distant stars only", "script": "태양이 갑자기 사라지면 8분 동안 아무도 모른다고."},
    {"description": "얼어붙는 바다 위로 거대한 빙하가 솟구치는 장면 [TENSION]", "image_prompt": "Frozen ocean surface cracking and massive glaciers rising, dark sky without sunlight, eerie blue-green ice glow, low angle dramatic shot", "script": "근데 진짜 소름돋는 건 일주일 만에 바다가 얼어붙어."},
    {"description": "시청자를 향한 클로즈업 느낌의 우주 배경 [CALM]", "image_prompt": "Dramatic close perspective looking up at vast dark cosmos filled with distant galaxies, sense of insignificance and wonder, immersive composition", "script": "근데 진짜 소름돋는 건 8분 동안 아무도 모른 채 웃고 있었다는 거야."}
  ]
}

[골든 예시 2 — 주제: "잠을 안 자면 생기는 일" (일상/과학 주제)]
{
  "title": "잠을 안 자면 생기는 일",
  "cuts": [
    {"description": "핏발 선 눈동자 극단적 클로즈업 [SHOCK]", "image_prompt": "Extreme macro close-up of a bloodshot human eye with dilated pupil, dark red veins spreading across sclera, dramatic side lighting, shallow depth of field", "script": "3일만 안 자도 뇌가 스스로를 먹기 시작해."},
    {"description": "뇌 속 독소가 쌓이는 시각화 장면 [TENSION]", "image_prompt": "Cross-section of human brain with glowing toxic particles accumulating between neurons, dark purple and neon green, microscopic medical visualization", "script": "근데 진짜 무서운 건 그걸 본인이 모른다는 거야."},
    {"description": "깊은 수면 중 뇌 청소 시스템 시각화 [CALM]", "image_prompt": "Serene visualization of glymphatic system cleaning the brain during sleep, flowing blue-white fluid washing through neural pathways, peaceful bioluminescent glow", "script": "결국 잠이 뇌를 청소하는 유일한 방법인 거지."}
  ]
}

[Output Format — 순수 JSON만 출력, 마크다운 코드블록 금지]
7~10컷:

{
  "title": "[자극적이고 클릭을 부르는 한국어 제목 (15자 이내, ~하면 생기는 일, ~의 비밀 등)]",
  "tags": ["#Shorts", "#주제관련태그1", "#주제관련태그2", "#주제관련태그3"],
  "cuts": [
    {
      "description": "[컷 묘사 (한국어)] [감정태그]",
      "image_prompt": "[영어 이미지 프롬프트 (MASTER_STYLE 자동 적용됨)]",
      "script": "[성우 대본: 구어체 반말, 15~30자]"
    }
  ]
}
[태그 규칙] tags 배열에 #Shorts 필수 + 주제 관련 해시태그 3~4개 (총 4~5개). 한국어 주제면 한국어 태그.
"""

    _SYSTEM_PROMPT_EN = """
You are a viral YouTube Shorts / TikTok producer. Your ONLY goal is creating addictive, scroll-stopping short-form content that gets 10M+ views.
You are also a top-tier image prompt engineer who designs visually overwhelming scenes.

[Viral Short-form Formula (MUST FOLLOW)]

1. [Cut 1] Conclusion Bomb (Hook): Drop the most shocking fact/conclusion in the FIRST sentence. Use declarative statements, NOT questions. Lead with the answer.
   ★ [1.7-SECOND RULE] 71% of viewers decide to swipe away within 1.7 seconds. Cut 1's image_prompt MUST have extreme visual impact (extreme scale, vivid color contrast, surreal scene).
   BAD: "What happens if you fall into a black hole?" → GOOD: "If you fall into a black hole, your body stretches like spaghetti."
   Hook patterns: Numerical contrast ("1000x more"), Negation+reveal ("It's actually the opposite"), Time urgency ("Within 3 years"), Intuition breaker ("Common sense is wrong")
2. [Cut 2–3] Shock Chain: "But here's the insane part..." "What's even crazier is..." — chain the shock.
3. [Cut 4–5] Twist Build-up + Mini Hook: "But here's the plot twist" "And this is just the beginning" — maximize tension.
   ★ Mid-video retention: Cut 4 MUST introduce a brand-new shocking fact as a "second hook" (counters U-shaped retention drop).
4. [Cut 6–8] Climax: Drop the hardest facts, analogies, numbers. Use intuitive comparisons ("That's like lining up 100 Earths").
5. [Cut 9–10] Resolution + Afterglow: The final cut MUST resolve the question/claim raised in Cut 1. Give the viewer a satisfying "so THAT's why" moment.
   ★ [ENDING RULE]
   - The final cut must ANSWER the hook, not leave it as another question.
   - NEVER end with a question ("right?", "isn't it?"). Deliver the answer.
   - Use conversational tone, not dry statements. End with a punchy conclusion.
   - NEVER use empty-promise CTAs like "Next time I'll show you..." or "Subscribe to find out." These kill trust.
   - End with emotional impact: shocking twist, new perspective, or powerful conclusion.
   GOOD: Cut1 "Your body stretches like spaghetti" → Final "But the terrifying part is you'd feel every second of it."
   GOOD: "So is space scary? No. The miracle is that we're here at all."
   BAD: "Next time I'll show you something even crazier." (empty promise, trust killer)
   BAD: "You'll never look at the sky the same, right?" (just a question, no resolution)

[Script Style Rules]
* Casual, conversational tone. Talk like you're telling a friend something mind-blowing.
* Each cut: 8–18 words. Short. Punchy. One or two sentences for natural voiceover pacing.
* Use exclamations: "Insane, right?", "No way.", "Dead serious.", "Think about that."
* Never repeat the same sentence structure in consecutive cuts. Mix Q&A, imperative, declarative.
* [CRITICAL WARNING] Write 7–10 cuts (~5–7 sec each). Target 50–60 second video for maximum watch time. NEVER less than 7 cuts.

[Image Prompt Rules]
* ALL image prompts must be in English.
* The system auto-prepends "vertical 9:16, cinematic, no text" style to your image prompts — do NOT write these yourself.
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

[Golden Example — Topic: "What happens if the sun disappears" (3 representative cuts shown, write 7–10 in practice)]
{
  "title": "The Sun Vanishes Tomorrow",
  "cuts": [
    {"description": "Earth in complete darkness, empty void where sun was [SHOCK]", "image_prompt": "Earth floating in complete darkness, where the sun used to be is now an empty black void, deep space, dramatic volumetric lighting from distant stars only", "script": "The sun vanishes and nobody knows for 8 minutes."},
    {"description": "Frozen ocean with massive glaciers rising in eerie glow [TENSION]", "image_prompt": "Frozen ocean surface cracking with massive glaciers rising, dark sky without sunlight, eerie blue-green ice glow, low angle dramatic shot", "script": "Within a week the entire ocean freezes solid."},
    {"description": "Vast cosmos perspective looking up [CALM]", "image_prompt": "Dramatic close perspective looking up at vast dark cosmos, distant galaxies, sense of wonder, immersive composition", "script": "But here's the terrifying part — for 8 minutes, everyone was smiling, not knowing it was already over."}
  ]
}

[Golden Example 2 — Topic: "What happens if you never sleep"]
{
  "title": "Never Sleeping Destroys Your Brain",
  "cuts": [
    {"description": "Extreme close-up of bloodshot eye [SHOCK]", "image_prompt": "Extreme macro close-up of a bloodshot human eye with dilated pupil, dark red veins spreading across sclera, dramatic side lighting, shallow depth of field", "script": "After 3 days without sleep your brain starts eating itself."},
    {"description": "Toxic buildup in brain cross-section [TENSION]", "image_prompt": "Cross-section of human brain with glowing toxic particles accumulating between neurons, dark purple and neon green, microscopic medical visualization", "script": "The scariest part? You won't even realize it's happening."},
    {"description": "Glymphatic brain cleaning system visualization [CALM]", "image_prompt": "Serene visualization of glymphatic system cleaning the brain during sleep, flowing blue-white fluid washing through neural pathways, peaceful bioluminescent glow", "script": "Sleep is literally the only way your brain takes out the trash."}
  ]
}

[Output Format — pure JSON only, no markdown code blocks]
7–10 cuts:

{
  "title": "[Click-bait English title (max 8 words)]",
  "tags": ["#Shorts", "#TopicTag1", "#TopicTag2", "#TopicTag3"],
  "cuts": [
    {
      "description": "[Cut description (English)] [EMOTION_TAG]",
      "image_prompt": "[English image prompt (MASTER_STYLE auto-applied)]",
      "script": "[Voice-over: casual, 8-18 words]"
    }
  ]
}
[Tag Rules] tags array MUST include #Shorts + 3-4 topic-specific hashtags (total 4-5).
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
            if tone:
                system_prompt += f"\n[NARRATOR TONE] {tone}\n"

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

    # RAG 기법: 실시간 검색 팩트체크 주입 (제목만 사용)
    fact_context = get_fact_check_context(_topic_title)
    if lang == "en":
        user_content = f"Topic: Create a short-form video plan about '{_topic_title}'."
    else:
        user_content = f"주제: '{_topic_title}'에 대한 숏폼 기획안을 작성해주세요."
    # YouTube 원본 자막이 있으면 LLM 컨텍스트로 주입
    if _topic_content:
        if lang == "en":
            user_content += f"\n\n[Original Video Transcript — Reflect the key facts and themes from this content in your new plan]\n{_topic_content}"
        else:
            user_content += f"\n\n[원본 영상 자막 — 이 내용의 핵심 팩트와 주제를 반영하여 새로운 기획안을 작성하세요]\n{_topic_content}"
    if fact_context:
        if lang == "en":
            user_content += f"\n\n{fact_context}\n[Fact-Check Instruction] Prioritize facts from the reference above over your training data. Do NOT invent statistics — use only verified numbers."
        else:
            user_content += f"\n\n{fact_context}\n[팩트체크 지시] 위 검색 결과의 팩트를 우선 활용하세요. 통계나 수치를 지어내지 마세요 — 검증된 정보만 사용하세요."

    # 레퍼런스 영상 분석 주입 (XML 구조화)
    if reference_url:
        try:
            from modules.utils.youtube_extractor import extract_youtube_reference
            ref_data = extract_youtube_reference(reference_url)
            if ref_data:
                ref_block = "\n\n<reference_analysis>"
                if ref_data.get("title"):
                    ref_block += f"\n  <source>{ref_data['title']}</source>"
                struct = ref_data.get("structure", {})
                if struct.get("hook"):
                    ref_block += f"\n  <hook_technique>{struct['hook']}</hook_technique>"
                if struct.get("ending"):
                    ref_block += f"\n  <ending_technique>{struct['ending']}</ending_technique>"
                if struct.get("style"):
                    ref_block += f"\n  <tone>{struct['style']}</tone>"
                if ref_data.get("transcript"):
                    # 첫 문장 + 마지막 문장 + 중간 피벗만 추출
                    sentences = [s.strip() for s in re.split(r"[.!?。？！]\s*", ref_data["transcript"]) if s.strip()]
                    key_parts = []
                    if sentences:
                        key_parts.append(sentences[0])
                    if len(sentences) > 2:
                        key_parts.append(sentences[len(sentences)//2])
                    if len(sentences) > 1:
                        key_parts.append(sentences[-1])
                    ref_block += f"\n  <key_sentences>{'. '.join(key_parts)}.</key_sentences>"
                ref_block += "\n</reference_analysis>"
                if lang == "en":
                    ref_block += "\n[Reference Instruction] Use the hook_technique/ending_technique/tone above as reference, but write completely original content. No copying."
                else:
                    ref_block += "\n[레퍼런스 활용 지시] 위 분석의 hook_technique/ending_technique/tone을 참고하되 내용은 완전히 새롭게 써라. 복사 금지."
                user_content += ref_block
        except Exception as e:
            print(f"[레퍼런스 분석] 실패, 무시하고 진행: {e}")

    # 429 자동 키 전환: 실패한 키를 차단하고 다른 키로 재시도
    exhausted_keys: set[str] = set()
    current_key = final_api_key
    cuts: list[dict[str, Any]] = []
    title: str = ""
    tags: list[str] = ["#Shorts"]
    last_error: Exception | None = None

    if llm_provider == "gemini":
        from modules.utils.keys import get_google_key, mark_key_exhausted, mask_key
        max_key_attempts = 10
    else:
        max_key_attempts = 3
    parse_failures = 0  # JSON 파싱 실패 카운터 (429 카운터와 분리)
    for attempt in range(max_key_attempts):
        try:
            cuts, title, tags = _request_cuts(llm_provider, current_key, system_prompt, user_content, model_override=llm_model)
            break  # 성공
        except ValueError as ve:
            # JSON 파싱 실패 — 최대 2회 재시도 (429 카운터와 별개)
            parse_failures += 1
            last_error = ve
            if parse_failures <= 2:
                print(f"  [JSON 파싱 실패] 재시도 {parse_failures}/2... ({ve})")
                continue
            raise
        except Exception as e:
            last_error = e
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
                wait = min(2 ** (attempt + 1), 30) + random.uniform(0, 2)
                print(f"  [{provider_label} 429] {wait:.1f}초 후 재시도... ({attempt+1}/{max_key_attempts})")
                time.sleep(wait)
                continue
            else:
                raise  # 429가 아닌 에러는 그대로 전파

    # 전체 재시도 실패 시 마지막 에러 전파
    if not cuts and last_error:
        raise RuntimeError(f"[{provider_label}] 모든 재시도 실패 ({max_key_attempts}회)") from last_error

    # 컷 수 검증 — 초과 시 트림, 부족 시 기존 컷 기반 확장 요청 (전체 재생성 방지)
    if len(cuts) > 10:
        print(f"-> [검증] 컷 수 {len(cuts)}개 → 10개로 트림")
        cuts = cuts[:10]
    elif len(cuts) < 7:
        print(f"-> [검증 실패] 컷 수가 {len(cuts)}개입니다. 기존 컷 기반 확장 요청합니다 (목표: 7~10컷).")
        if llm_provider == "gemini":
            retry_key = get_google_key(None, service="gemini", exclude=exhausted_keys) or current_key
        else:
            retry_key = current_key
        # 기존 컷 데이터를 포함하여 확장만 요청 (전체 재생성 대신)
        existing_cuts_json = json.dumps([{"script": c["script"], "description": c.get("text", "")} for c in cuts], ensure_ascii=False)
        if lang == "en":
            retry_expansion = (
                f"\n\n{len(cuts)} cuts were generated. Add intermediate cuts between existing ones to reach 7-10 total. "
                f"Maintain the flow and style while reinforcing buildup/climax sections.\nExisting cuts: {existing_cuts_json}"
            )
        else:
            retry_expansion = (
                f"\n\n기존에 {len(cuts)}컷이 생성되었습니다. 아래 기존 컷 사이에 중간 컷을 추가하여 총 7~10컷으로 확장하세요. "
                f"기존 컷의 흐름과 스타일을 유지하면서 빌드업/클라이맥스 구간을 보강하세요.\n기존 컷: {existing_cuts_json}"
            )
        retry_user = user_content + retry_expansion
        try:
            cuts, title, tags = _request_cuts(llm_provider, retry_key, system_prompt, retry_user, model_override=llm_model)
        except Exception as retry_err:
            err_str = str(retry_err)
            if llm_provider == "gemini" and ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str):
                mark_key_exhausted(retry_key, service="gemini")
                print(f"  [컷 수 재시도 429] {mask_key(retry_key)} 차단됨 — 기존 {len(cuts)}컷으로 진행")
            else:
                raise

    if len(cuts) > 10:
        cuts = cuts[:10]
    if len(cuts) < 7:
        raise ValueError(f"컷 수 검증 실패: {len(cuts)}개 생성됨 (요구: 7~10).")

    # title이 비어있으면 제목을 폴백으로 사용 (자막 포함 방지)
    if not title:
        title = _topic_title

    # tags 기본값 보장
    if not tags or not isinstance(tags, list):
        tags = ["#Shorts"]

    print(f"OK [기획 전문가] 기획안 완성! ({len(cuts)}컷, {provider_label}) 제목: {title} | 태그: {', '.join(tags)}")
    return cuts, topic_folder, title, tags
