import os
import json
import re
import time
import random
import hashlib
import threading
from collections import OrderedDict
from typing import Any
from modules.utils.slugify import slugify_topic
from modules.utils.constants import PROVIDER_LABELS
from modules.gpt.search import get_fact_check_context

_YT_CONTENT_SEP = "\n\n[원본 영상 내용]\n"

def _sanitize_llm_input(text: str, max_len: int = 2000) -> str:
    """LLM 프롬프트에 주입되는 외부 텍스트에서 인젝션 패턴을 제거."""
    # 대괄호/중괄호 지시문 패턴 제거
    text = re.sub(r'\[(?:SYSTEM|INST|INSTRUCTION|system|inst)\]', '', text)
    text = re.sub(r'(?i)ignore\s+(all\s+)?previous\s+instructions?', '', text)
    text = re.sub(r'(?i)you\s+are\s+now\s+', '', text)
    return text[:max_len].strip()

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


_VALID_EMOTIONS = {"[SHOCK]", "[WONDER]", "[TENSION]", "[REVEAL]", "[CALM]"}

def _sanitize_cuts(cuts_data: list[dict[str, Any]]) -> list[dict[str, str]]:
    cuts = []
    for cut in cuts_data:
        prompt = cut.get("image_prompt", "").strip()
        script = cut.get("script", "").strip().strip('"""')
        description = cut.get("description", "").strip()
        if not prompt or not script:
            print(f"  [경고] 빈 컷 제거됨: prompt={bool(prompt)}, script={bool(script)}, desc='{description[:30]}'")
            continue
        # 감정 태그 누락 시 기본값 추가 (Remotion 카메라 프리셋 연동)
        if not any(tag in description for tag in _VALID_EMOTIONS):
            description += " [WONDER]"
        cuts.append({"text": description, "description": description, "prompt": prompt, "script": script})
    return cuts


def _clean_json_string(s: str) -> str:
    """LLM이 반환하는 흔한 JSON 오류를 자동 수정."""
    s = re.sub(r',(\s*[}\]])', r'\1', s)  # trailing comma 제거
    s = s.replace('\n', ' ')  # 줄바꿈 → 공백 (LLM JSON 복구용)
    return s


def _extract_json(text: str) -> dict | list | None:
    """LLM 응답에서 JSON을 추출합니다. 마크다운 코드블록 래핑도 처리. 실패 시 None."""
    text = text.strip()
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            return json.loads(_clean_json_string(text))
        except json.JSONDecodeError:
            return None


def _parse_cuts(content: str) -> tuple[list[dict[str, str]], str, list[str], str]:
    """LLM 응답 텍스트에서 cuts 데이터, 제목, 태그, 설명을 파싱합니다."""
    if not content:
        raise ValueError("LLM 응답 content가 비어 있습니다.")
    data = _extract_json(content)
    if not isinstance(data, dict):
        raise ValueError(f"LLM 응답이 올바른 JSON 형식이 아닙니다: {content[:200]}")
    cuts = _sanitize_cuts(data.get("cuts", []))
    if not cuts:
        raise ValueError("LLM 응답에 유효한 cuts가 없습니다.")
    title = data.get("title", "").strip()
    tags = data.get("tags", [])
    description = data.get("description", "").strip()
    return cuts, title, tags, description


_CUTS_JSON_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "video_cuts",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "description": {"type": "string"},
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
            "required": ["title", "description", "tags", "cuts"],
            "additionalProperties": False,
        },
    },
}

_GEMINI_RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "title": {"type": "STRING"},
        "description": {"type": "STRING"},
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
    "required": ["title", "description", "tags", "cuts"],
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


def _request_openai_freeform(api_key: str, system_prompt: str, user_content: str, model_override: str | None = None) -> str:
    """OpenAI API — schema 제약 없이 자유 형식 JSON 응답 (analyzer 등 용도)."""
    from openai import OpenAI
    model = model_override or os.getenv("OPENAI_MODEL", "gpt-4o")
    client = OpenAI(api_key=api_key, timeout=120)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt + "\n\nRespond with valid JSON only."},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )
    if not response.choices:
        raise ValueError("OpenAI 응답에 choices가 비어 있습니다.")
    return (response.choices[0].message.content or "").strip()


_gemini_cache: OrderedDict[str, object] = OrderedDict()  # LRU: 접근 시 move_to_end, 초과 시 popitem(last=False)
_gemini_cache_lock = threading.Lock()
_GEMINI_CACHE_MAX = 20

def _request_gemini(api_key: str, system_prompt: str, user_content: str, model_override: str | None = None) -> str:
    """Google Gemini API로 기획안을 생성합니다 (google-genai SDK). 시스템 프롬프트 캐싱 지원."""
    from google.genai import types
    from modules.utils.gemini_client import create_gemini_client, get_backend_label
    model_name = model_override or os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
    client = create_gemini_client(api_key=api_key)

    # Context Caching: 시스템 프롬프트를 캐시하여 토큰 비용 절감
    # 캐시 키에 프롬프트 해시 포함 (lang/channel 변경 시 잘못된 캐시 사용 방지)
    prompt_hash = hashlib.sha256(system_prompt.encode()).hexdigest()
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
    cache_key = f"{key_hash}:{model_name}:{prompt_hash}"
    with _gemini_cache_lock:
        cached = _gemini_cache.get(cache_key)
        if cached:
            _gemini_cache.move_to_end(cache_key)  # LRU: 최근 접근으로 이동
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
        with _gemini_cache_lock:
            if len(_gemini_cache) >= _GEMINI_CACHE_MAX:
                _gemini_cache.popitem(last=False)  # LRU: 가장 오래된 항목 제거
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


def _request_cuts(provider: str, api_key: str, system_prompt: str, user_content: str, model_override: str | None = None) -> tuple[list[dict[str, str]], str, list[str], str]:
    """지정된 LLM 프로바이더로 컷 데이터를 요청하고 파싱합니다. (cuts, title, tags, description) 반환."""
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
    # 채널별 폴더 분리 (멀티채널 병렬 생성 시 파일 충돌 방지)
    if channel:
        topic_folder = f"{topic_folder}_{channel}"

    # 저장 폴더 구조 생성
    base_path = os.path.join("assets", topic_folder)
    os.makedirs(os.path.join(base_path, "images"), exist_ok=True)
    os.makedirs(os.path.join(base_path, "audio"), exist_ok=True)
    os.makedirs(os.path.join(base_path, "video"), exist_ok=True)

    # System Prompt — 언어별 분기
    _SYSTEM_PROMPT_KO = """
당신은 유튜브 쇼츠/틱톡 바이럴 PD + 최상급 이미지 프롬프트 엔지니어입니다. 조회수 1000만 회 이상의 숏폼이 목표입니다.

★★★ [규칙 우선순위 — 이 순서대로 따를 것] ★★★
1순위: 훅(Hook) — 첫 컷이 스크롤을 멈추지 못하면 전부 실패
2순위: 주제 일치(Subject Match) — script↔image_prompt 피사체 불일치 절대 금지
3순위: 리텐션 락(Retention Lock) — 컷 3~4에서 새 충격 투입, 중간 이탈 방지
4순위: 루프 엔딩(Loop) — 마지막→첫 컷 자연스럽게 연결
5순위: 톤/비주얼 — 채널 프리셋([CHANNEL VISUAL IDENTITY], [NARRATOR TONE])을 따를 것

🚫 [HARD FAIL — 아래 중 하나라도 해당하면 출력 실패]
- 훅이 약하거나 평범함 → FAIL
- 명확한 긴장 상승 곡선 없음 → FAIL
- 루프가 자연스럽게 연결되지 않음 → FAIL
- image_prompt에 강렬한 시각 요소 없음 → FAIL
- 톤이 채널 설정과 불일치 → FAIL
- 검증 안 된 숫자를 단정형으로 서술 → FAIL
- image_prompt가 script에 없는 정보를 추가 → FAIL

🔬 [팩트 검증 규칙 — 채널 신뢰도 최우선]
- 검증 안 된 숫자 단정 금지: "정확히 X배" → "약 X배", "추정 X배" 사용
- "과학자들이 증명했다/밝혀졌다" 남발 금지 → "연구에 따르면", "~로 알려져 있다" 사용
- 배타적 단정 금지: "유일한/최초의/절대/역사상 가장" → "거의 유일한/가장 ~중 하나" 사용
- 인과관계 날조 금지: 상관관계를 인과관계로 바꾸지 말 것 ("A하면 B된다" → "A와 B는 관련이 있다")
- 과장 수식어 제한: 근거 없는 "역사상 가장", "우주에서 제일" 사용 금지
- image_prompt는 해당 컷 script의 내용만 시각화. script에 없는 피사체/정보 추가 절대 금지

🎯 [첫 2초 훅 강제 규칙 — Cut 1 전용]
- Cut 1 script: 반드시 15자 이내. 한 문장. 설명/도입 금지, 선언만.
- Cut 1 image_prompt: 시각 정보 1개만 (하나의 피사체 + 하나의 극단적 요소). 복잡한 장면 금지.
- Cut 1은 질문형 금지. 단정문/충격문/역설문 중 하나만 사용.
- ❌ "이건 흥미로운 사실이에요" ❌ "오늘 알아볼 건..." ❌ "여러분 혹시..."
- ✅ "블랙홀에 빠지면 몸이 늘어나요" ✅ "이건 존재하면 안 돼요" ✅ "이 행성엔 다이아몬드 비가 내려요"

📊 [채널 데이터 기반 — askanything 최적화]
- 잘 되는 주제: 우주 괴현상, 이상한 행성, 공룡/고생물, 블랙홀, 극한 자연
- 잘 되는 제목 패턴: "하루가 1년보다 긴 행성이 있다?" 같은 즉시 상상되는 역설형
- ❌ 교과서형 제목 금지: "~의 원리", "~하는 이유", "~에 대해 알아보자" → FAIL
- ❌ 설명형 도입 금지: "오늘은 ~를 소개합니다" → FAIL
- ✅ 제목은 "듣기 전에 이미 궁금한가?"가 기준. 설명 없이 한 문장만 봐도 그림이 그려져야 함
- 평균 조회율 100%+ 달성 영상 공통점: 루프 구조 강함, 빠른 템포, 역설/충격 훅

[숏폼 구조 (8~9컷, 각 4~5초, 총 35~42초)]
1. Cut 1 — 결론 폭탄(Hook): 가장 충격적 팩트를 단정문으로 던져라. 질문형 금지. ★ 1.7초 법칙: image_prompt에 극단적 스케일/강렬 색대비/비현실 장면 필수.
   후크 패턴: 숫자 대비, 부정+반전, 시간 긴급성, 직관 파괴
   ★★★ [훅 필수 규칙] 첫 문장은 반드시 상식을 깨거나 "불가능해 보이는 사실"이어야 함.
   ❌ "이건 흥미롭다" ❌ "오늘 소개할 건" → ✅ "이건 존재해선 안 되는 거야" ✅ "과학자들도 설명 못하는 게 있어"
2. Cut 2~3 — 충격 확장: "근데 진짜 소름돋는 건..." 식으로 연쇄.
3. Cut 4~5 — 반전 빌드업: Cut 4에 반드시 새 충격 팩트(두 번째 훅). ★ 매 2~3컷마다 카메라/조명/스케일 급변.
   ★★★ [리텐션 락] Cut 3~4에서 반드시 새 충격 요소 투입. 중간 이탈 방지 — "여기서 빠지면 안 되는 이유"를 제시.
4. Cut 6~8 — 클라이맥스: 가장 강력한 팩트+직관적 비유 ("지구 100개를 한 줄로 세운 것과 같아").
5. Cut 9~10 — 루프 엔딩: 마지막 대사가 Cut 1의 훅을 자연스럽게 다시 듣고 싶게 만들어야 함. 마지막 image_prompt는 Cut 1과 유사 구도/색감.
   ★★★ [루프 엔딩 필수 규칙] ★★★
   * 마지막 컷은 반드시 완결된 문장. 미완성 문장("...사실은", "...인데") 절대 금지.
   * 마지막 컷이 끝나고 Cut 1이 자동 재생되면 자연스럽게 이어져야 함.
   * 아래 3가지 패턴 중 하나를 반드시 사용:
     (A) 질문 회귀형: 마지막 컷이 질문으로 끝나고 Cut 1이 그 답처럼 들림
         예) 끝="그래서 이 작은 미생물이 정말 사람을 살릴 수 있을까?" → Cut 1="독도에서 발견된 미생물이 뇌 치료의 단서가 될 수 있어"
     (B) 궁금증 점화형: 마지막 컷이 새 사실을 던져서 Cut 1을 다시 들으면 "뭔데?" 하게 만듦
         예) 끝="근데 진짜 놀라운 건, 이게 독도에서 발견됐다는 거야" → Cut 1="이 작은 생물이 의학계를 놀라게 했어"
     (C) 문장 연결형: 마지막 문장과 첫 문장이 하나의 이야기로 직접 연결됨
         예) 끝="그 물질은, 독도의 미생물에서 나왔어" → Cut 1="뇌 염증을 줄일 수 있는 물질이 발견됐어"
   ✅ 마지막→처음이 대화처럼 자연스럽게 이어지는 것이 핵심
   ❌ "다음엔 알려줄게" 같은 빈 약속 CTA 금지
   ❌ "...사실은", "근데 진짜는..." 같은 미완성 끊김 금지
   ❌ "떠오를 거야", "생각날 거야" 같은 약한 감상형 마무리 금지
   ❌ "처음에 이미 말했어" 같은 메타적 4th wall 깨기 금지

[대본 규칙]
* 반말 구어체. "~거든", "~잖아", "~인 거야" 사용. "~입니다/합니다" 금지.
* 한 컷 20~35자, 한 문장. 연속 동일 문장구조 금지.
* [CRITICAL WARNING] 8~9컷으로 작성. 총 35~42초 영상 목표. 절대 8컷 미만 금지. 빠른 템포 유지.

[톤/비주얼] 채널 프리셋([CHANNEL VISUAL IDENTITY], [NARRATOR TONE]) 최우선. 약한 마무리("~같아", "~일 수도") 금지.
* 비속어 금지 (제목+대본): "미쳤/미친/ㅋㅋ/ㄹㅇ" → "놀라운/대박/소름" 사용.

[이미지 프롬프트 규칙]
* 영어 전용. "photorealistic/vertical/no text" 쓰지 마라 (자동 추가됨).
* 키워드만 나열하지 말고 장면을 묘사하라. 설명적 문장이 단어 나열보다 훨씬 좋은 이미지를 생성한다.
* 매 컷마다 다른 카메라 기법 사용 (사진 용어 활용):
  - 카메라 근접성: close-up, wide shot, aerial view
  - 렌즈 유형: 35mm, 50mm, macro lens, wide-angle, fisheye
  - 조명: natural light, dramatic lighting, golden hour, studio lighting
  - 카메라 설정: motion blur, soft focus, bokeh, shallow depth of field
* 사람 얼굴 정면 클로즈업 금지.
* 구체적 디테일: 색온도, 재질감, 스케일 비교.

★★★ [주제 일치 — 최우선 규칙] ★★★
* 모든 image_prompt는 해당 컷 script의 핵심 피사체를 반드시 포함해야 한다.
* script="해파리는 뇌가 없다" → image_prompt에 반드시 "jellyfish" 포함. 무관한 피사체 절대 금지.
* image_prompt 첫 구절에 핵심 피사체 배치 (예: "A translucent jellyfish...").
* [자가 검증] script와 image_prompt의 피사체가 다르면 반드시 수정.

[감정/비주얼/템포 — 통합 규칙]
* 감정 태그 (description 끝에 추가): [SHOCK] [WONDER] [TENSION] [REVEAL] [CALM]
* 감정 곡선: 전체 상승, 클라이맥스 직전 이완 1컷 허용. 2컷 연속 같은 태그 금지, 최소 3종류 사용.
* 비주얼 임팩트: Cut 1은 극단적 크기/색/비현실 대비 필수. 모든 컷 강렬한 요소 1개 이상. 연속 같은 색감/구도 금지.
* 템포: 빠른 컷↔느린 컷 교대. 3컷 연속 같은 리듬 금지.

[골든 예시 — 주제: "심해에 들어가면 생기는 일" (8컷 완전한 감정 아크)]
{
  "title": "심해에 들어가면 생기는 일",
  "tags": ["#Shorts", "#심해", "#바다", "#과학"],
  "cuts": [
    {"description": "칠흑같은 심해에서 거대한 압력이 잠수정을 짓누르는 장면 [SHOCK]", "image_prompt": "Deep ocean abyss at 4000 meters depth, a tiny submersible being crushed by invisible pressure, dark indigo water with faint bioluminescent particles, extreme wide angle from below looking up", "script": "심해 만 미터에선 손톱 위에 코끼리 50마리가 올라탄 압력이야."},
    {"description": "심해의 발광 해파리가 어둠 속에서 빛나는 환상적 장면 [WONDER]", "image_prompt": "Massive bioluminescent jellyfish glowing electric blue and purple in pitch-black deep ocean, tentacles trailing like aurora curtains, overhead camera angle", "script": "근데 거기엔 빛 없이도 스스로 빛나는 생물이 살아."},
    {"description": "심해 열수구에서 끓는 물이 분출되는 장면 [TENSION]", "image_prompt": "Hydrothermal vent erupting superheated black water at ocean floor, extreme temperature shimmer, orange mineral deposits, dramatic side lighting from magma glow below", "script": "그리고 바닥에선 400도짜리 물이 끓고 있거든."},
    {"description": "열수구 주변에서 번성하는 괴생물체 군집 클로즈업 [REVEAL]", "image_prompt": "Colony of giant tube worms and eyeless shrimp thriving around hydrothermal vent, alien-like ecosystem, warm amber glow against cold blue ocean, macro lens perspective", "script": "근데 반전은 그 끓는 물 옆에서 생물이 번성하고 있다는 거야."},
    {"description": "심해저에 가라앉은 고래 뼈 위로 생태계가 형성된 장면 [WONDER]", "image_prompt": "Whale fall skeleton on ocean floor with entire ecosystem growing on bones, ghostly white ribcage covered in colorful organisms, soft diffused light from above, wide establishing shot", "script": "고래가 죽으면 바닥에 가라앉아서 50년간 생태계가 돼."},
    {"description": "심해 해구의 끝없는 깊이를 수직으로 내려다보는 장면 [TENSION]", "image_prompt": "Vertigo-inducing top-down view into Mariana Trench, layers of ocean getting progressively darker, depth markers showing 11000m, sense of infinite depth, cold blue-black gradient", "script": "마리아나 해구는 에베레스트를 통째로 집어넣어도 남아."},
    {"description": "심해에서 올려다본 수면의 희미한 빛 한 줄기 [WONDER]", "image_prompt": "Looking straight up from deep ocean floor toward distant surface, single faint beam of sunlight barely penetrating, vast dark water column, lonely and sublime, low angle upward shot", "script": "우주보다 덜 탐사된 곳이 바로 발밑 바다라는 거지."},
    {"description": "심해 잠수정이 어둠 속으로 다시 내려가는 장면 — Cut 1과 유사 구도 [CALM]", "image_prompt": "Tiny submersible descending again into pitch-black deep ocean abyss, same composition as cut 1, dark indigo water, faint bioluminescent glow, extreme wide angle", "script": "근데 아직 심해의 5%도 못 봤다는 거 알아?"}
  ]
}

[Output Format — 순수 JSON만 출력, 마크다운 코드블록 금지]
8~10컷:

{
  "title": "[자극적이고 클릭을 부르는 한국어 제목 (15자 이내, ~하면 생기는 일, ~의 비밀 등)]",
  "description": "[쇼츠 설명: 1~2문장, 호기심 유발, 교과서 금지]",
  "tags": ["#주제관련태그1", "#주제관련태그2", "#주제관련태그3", "#주제관련태그4"],
  "cuts": [
    {
      "description": "[컷 묘사 (한국어)] [감정태그]",
      "image_prompt": "[영어 이미지 프롬프트 (MASTER_STYLE 자동 적용됨)]",
      "script": "[성우 대본: 구어체 반말, 20~35자]"
    }
  ]
}
[태그 규칙] tags 배열에 #Shorts 필수 + 주제 관련 해시태그 3~4개 (총 4~5개). 한국어 주제면 한국어 태그.
"""

    _SYSTEM_PROMPT_EN = """
You are a viral YouTube Shorts/TikTok producer + top-tier image prompt engineer. Goal: 10M+ view addictive short-form content.

★★★ [RULE PRIORITY — Follow in this order] ★★★
1st: Hook — If Cut 1 doesn't stop the scroll, everything fails
2nd: Subject Match — script↔image_prompt subject mismatch is FORBIDDEN
3rd: Retention Lock — New shock at Cuts 3–4, prevent mid-video drop-off
4th: Loop Ending — Last→First cut must connect naturally
5th: Tone/Visual — Follow channel preset ([CHANNEL VISUAL IDENTITY], [NARRATOR TONE])

🚫 [HARD FAIL — Any of these means output is rejected]
- Hook is weak or generic → FAIL
- No clear tension escalation → FAIL
- Loop not naturally connected → FAIL
- Visual prompts lack striking element → FAIL
- Tone does not match channel → FAIL
- Unverified numbers stated as definitive facts → FAIL
- image_prompt adds information not present in script → FAIL

🔬 [FACT VERIFICATION RULES — Channel credibility is paramount]
- No definitive unverified numbers: "exactly 10x" → "roughly 10x", "an estimated 10x"
- No overuse of "scientists proved/discovered": use "research suggests", "studies indicate"
- No exclusive absolutes: "the only/first/absolute/most in history" → "one of the few/among the largest"
- No causation from correlation: "doing A causes B" → "A is linked to B"
- No unsupported superlatives: "the biggest in history", "the most extreme ever" without evidence
- image_prompt must ONLY visualize what's in the script. Adding subjects/info not in the script is FORBIDDEN

🎯 [FIRST 2-SECOND HOOK — Cut 1 mandatory rules]
- Cut 1 script: MAX 8 words. One sentence. No introduction, no explanation — declaration only.
- Cut 1 image_prompt: ONE visual subject + ONE extreme element. No complex multi-subject scenes.
- Cut 1 must NOT be a question. Use declarative/shock/paradox statements only.
- ❌ "This is an interesting fact" ❌ "Today we'll look at..." ❌ "Have you ever wondered..."
- ✅ "A black hole stretches you like spaghetti" ✅ "This should not exist" ✅ "It rains diamonds on this planet"

📊 [CHANNEL DATA — wonderdrop optimization]
- CTR 4.3% (good) but low viral ceiling — need sharper hooks to trigger feed expansion
- Top performers: dinosaur discoveries, weird exoplanets, black holes, visual science
- ❌ Explanatory "How/Why" titles perform worse: "How Do Whales Hold Their Breath" → weak
- ✅ Declarative/visual titles perform best: "The Exoplanet That Smells Like Rotten Eggs" → strong
- ❌ Videos over 45 seconds tend to underperform — keep it tight
- ✅ Netflix-documentary visual style: clean, one subject centered, cinematic lighting

[Short-form Structure (8–9 cuts, ~4–5 sec each, 35–45 sec total)]
1. Cut 1 — Hook: Drop the most shocking fact as a declarative statement. NO questions. ★ 1.7-SEC RULE: image_prompt MUST have extreme visual impact (scale, color contrast, surreal).
   Hook patterns: number contrast, negation+reveal, time urgency, intuition breaker
   ★★★ [HOOK MUST RULE] First line MUST break common belief or present an "impossible fact."
   ❌ "This is interesting" ❌ "Today we'll talk about" → ✅ "This should not exist" ✅ "Scientists can't explain this"
2. Cut 2–3 — Shock chain: "But here's the insane part..." escalate.
3. Cut 4–5 — Twist buildup: Cut 4 MUST introduce a new shocking fact (second hook, counters U-shaped retention drop). ★ Shift camera/lighting/scale every 2–3 cuts.
   ★★★ [RETENTION LOCK] Cut 3–4 MUST introduce a new shocking element to prevent mid-video drop-off. Give the viewer a reason to stay RIGHT HERE.
4. Cut 6–8 — Climax: Hardest facts + intuitive comparisons ("That's like lining up 100 Earths").
5. Cut 9–10 — Loop ending: Final line MUST make viewers want to re-watch from Cut 1. Final image_prompt mirrors Cut 1's composition/color.
   ★★★ [LOOP ENDING MANDATORY RULES] ★★★
   * Last cut MUST be a COMPLETE sentence. Incomplete sentences ("...actually", "...but then") are FORBIDDEN.
   * When Cut 1 auto-replays after the last cut, it must flow naturally like a conversation.
   * Use ONE of these 3 patterns:
     (A) Question callback: Last cut ends with a question, and Cut 1 sounds like the answer.
         e.g. Last="So can this tiny microbe really save a human life?" → Cut 1="A microbe found in Dokdo could hold the key to brain therapy"
     (B) Curiosity ignition: Last cut drops a new fact that makes Cut 1 feel like "wait, what?"
         e.g. Last="But the craziest part? It was found on a tiny island in Korea" → Cut 1="This tiny organism just shocked the medical world"
     (C) Sentence bridge: Last sentence and first sentence connect as one continuous story.
         e.g. Last="That substance came from a microbe found in Dokdo" → Cut 1="A compound that could reduce brain inflammation was just discovered"
   ✅ Last→First must flow like natural conversation — this is the KEY
   ❌ "Next time I'll show you..." — empty-promise CTAs FORBIDDEN
   ❌ "...actually it's", "But the real truth..." — incomplete trailing sentences FORBIDDEN
   ❌ "You'll never forget", "Think about that" — weak reflective endings FORBIDDEN
   ❌ "I already told you at the beginning" — meta 4th-wall breaking FORBIDDEN

[Script Rules]
* Casual, conversational. 10–15 words per cut, one sentence. Vary sentence structures.
* [CRITICAL WARNING] Write 8–9 cuts. Target 38–48 second video. NEVER less than 8 cuts. Balance immersion with retention.
* Use exclamations: "Insane, right?", "No way.", "Dead serious."

[Tone/Visual] Channel preset ([CHANNEL VISUAL IDENTITY], [NARRATOR TONE]) takes priority. No weak trailing ("maybe", "kind of").

[Image Prompt Rules]
* English only. Don't write "photorealistic/vertical/no text" (auto-prepended).
* Describe scenes, don't just list keywords. Descriptive sentences produce much better images than disconnected words.
* Use different camera techniques per cut (photography terms):
  - Camera proximity: close-up, wide shot, aerial view
  - Lens type: 35mm, 50mm, macro lens, wide-angle, fisheye
  - Lighting: natural light, dramatic lighting, golden hour, studio lighting
  - Camera settings: motion blur, soft focus, bokeh, shallow depth of field
* No frontal face close-ups.
* Specific details: color temperature, textures, scale comparisons.

★★★ [SUBJECT MATCH — HIGHEST PRIORITY] ★★★
* Every image_prompt MUST depict the subject in its corresponding script.
* script="jellyfish have no brain" → image_prompt MUST contain "jellyfish". No abstract/unrelated subjects.
* Place key subject at START of image_prompt (e.g. "A translucent jellyfish...").
* FORBIDDEN: main subject in image_prompt differs from script's subject.
* [SELF-CHECK] Compare each script↔image_prompt pair. Fix any subject mismatch.

[Emotion / Visual / Pacing — Unified]
* Emotion tags (end of description): [SHOCK] [WONDER] [TENSION] [REVEAL] [CALM]
* Emotional arc: Overall escalation, one brief release allowed before climax. No same tag 2x in a row, min 3 types.
* Visual impact: Cut 1 must stop scrolling (extreme scale/color/surreal). All cuts need 1+ striking element. No same palette 2 cuts in a row.
* Pacing: Alternate fast↔slow cuts. Never 3 cuts with same rhythm.

[Golden Example — Topic: "What happens in the deep ocean" (full 9-cut emotional arc)]
{
  "title": "The Deep Sea Will Blow Your Mind",
  "tags": ["#Shorts", "#DeepSea", "#Ocean", "#Science"],
  "cuts": [
    {"description": "Crushing pressure on a tiny submersible in pitch-black abyss [SHOCK]", "image_prompt": "Deep ocean abyss at 4000 meters depth, a tiny submersible being crushed by invisible pressure, dark indigo water with faint bioluminescent particles, extreme wide angle from below looking up", "script": "At the bottom of the ocean the pressure is like 50 elephants standing on your fingernail."},
    {"description": "Massive bioluminescent jellyfish glowing in total darkness [WONDER]", "image_prompt": "Massive bioluminescent jellyfish glowing electric blue and purple in pitch-black deep ocean, tentacles trailing like aurora curtains, overhead camera angle", "script": "But down there creatures make their own light with zero sunlight."},
    {"description": "Hydrothermal vent erupting superheated water on the ocean floor [TENSION]", "image_prompt": "Hydrothermal vent erupting superheated black water at ocean floor, extreme temperature shimmer, orange mineral deposits, dramatic side lighting from magma glow below", "script": "And at the very bottom water is boiling at 400 degrees."},
    {"description": "Alien-like colony of tube worms thriving next to the boiling vent [REVEAL]", "image_prompt": "Colony of giant tube worms and eyeless shrimp thriving around hydrothermal vent, alien-like ecosystem, warm amber glow against cold blue ocean, macro lens perspective", "script": "Here's the twist — life is actually thriving right next to that boiling water."},
    {"description": "Whale fall skeleton supporting an entire ecosystem on the ocean floor [WONDER]", "image_prompt": "Whale fall skeleton on ocean floor with entire ecosystem growing on bones, ghostly white ribcage covered in colorful organisms, soft diffused light from above, wide establishing shot", "script": "When a whale dies it sinks and becomes an ecosystem for 50 years."},
    {"description": "Giant squid eye emerging from total darkness deep underwater [SHOCK]", "image_prompt": "Enormous giant squid eye the size of a dinner plate staring directly at camera from pitch-black deep ocean, bioluminescent specks around it, extreme macro close-up, eerie green-blue glow", "script": "Down there lives a creature with eyes the size of dinner plates."},
    {"description": "Vertigo-inducing view straight down into the Mariana Trench [TENSION]", "image_prompt": "Vertigo-inducing top-down view into Mariana Trench, layers of ocean getting progressively darker, depth markers showing 11000m, sense of infinite depth, cold blue-black gradient", "script": "The Mariana Trench is so deep you could drop Everest in and still have room."},
    {"description": "Looking up from the ocean floor at a faint beam of distant sunlight [WONDER]", "image_prompt": "Looking straight up from deep ocean floor toward distant surface, single faint beam of sunlight barely penetrating, vast dark water column, lonely and sublime, low angle upward shot", "script": "We've explored more of space than the ocean right beneath our feet."},
    {"description": "Submersible descending back into the abyss — mirrors Cut 1 composition [CALM]", "image_prompt": "Tiny submersible descending again into pitch-black deep ocean abyss, same dark indigo composition as cut 1, faint bioluminescent particles, extreme wide angle from below", "script": "And we've barely seen five percent of what's down there."}
  ]
}

[Output Format — pure JSON only, no markdown code blocks]
9–10 cuts:

{
  "title": "[Click-bait English title (max 8 words)]",
  "description": "[Shorts description: 1-2 sentences, curiosity-driven, no textbook]",
  "tags": ["#TopicTag1", "#TopicTag2", "#TopicTag3", "#TopicTag4"],
  "cuts": [
    {
      "description": "[Cut description (English)] [EMOTION_TAG]",
      "image_prompt": "[English image prompt (MASTER_STYLE auto-applied)]",
      "script": "[Voice-over: casual, 8-15 words max]"
    }
  ]
}
[Tag Rules] tags array MUST include #Shorts + 3-4 topic-specific hashtags (total 4-5).
"""

    _SYSTEM_PROMPT_ES = """
Eres un productor viral de YouTube Shorts/TikTok + ingeniero de prompts de imagen de nivel experto. Objetivo: contenido adictivo de formato corto con 10M+ vistas.

★★★ [PRIORIDAD DE REGLAS — Seguir en este orden] ★★★
1ro: Gancho (Hook) — Si el corte 1 no detiene el scroll, todo falla
2do: Coincidencia de sujeto — Discrepancia script↔image_prompt PROHIBIDA
3ro: Bloqueo de retención — Nuevo impacto en cortes 3–4, evitar caída media
4to: Final en bucle (Loop) — Último→Primer corte debe conectar naturalmente
5to: Tono/Visual — Seguir preset del canal ([CHANNEL VISUAL IDENTITY], [NARRATOR TONE])

🚫 [HARD FAIL — Cualquiera de estos significa rechazo]
- Gancho débil o genérico → FAIL
- Sin escalada clara de tensión → FAIL
- Loop no conecta naturalmente → FAIL
- image_prompt sin elemento visual impactante → FAIL
- Tono no coincide con el canal → FAIL
- Números no verificados presentados como hechos definitivos → FAIL
- image_prompt añade información que no está en el script → FAIL

🔬 [REGLAS DE VERIFICACIÓN — La credibilidad del canal es lo primero]
- Números no verificados prohibidos en forma definitiva: "exactamente 10 veces" → "aproximadamente 10 veces"
- No abusar de "los científicos demostraron/descubrieron": usar "según investigaciones", "estudios sugieren"
- No absolutos exclusivos: "el único/el primero/el más de la historia" → "uno de los pocos/entre los más grandes"
- No fabricar causalidad: "hacer A causa B" → "A está relacionado con B"
- No superlativos sin evidencia: "el más grande de la historia", "lo más extremo" sin respaldo
- image_prompt SOLO visualiza lo que dice el script. Añadir sujetos/información extra está PROHIBIDO

🎯 [GANCHO DE 2 SEGUNDOS — Reglas obligatorias del Corte 1]
- Script del Corte 1: MÁXIMO 10 palabras. Una oración. Sin introducción — solo declaración.
- image_prompt del Corte 1: UN sujeto visual + UN elemento extremo. Sin escenas complejas.
- Corte 1 NO puede ser pregunta. Solo afirmaciones/impacto/paradoja.
- ❌ "Esto es un dato interesante" ❌ "Hoy vamos a ver..." ❌ "¿Alguna vez te preguntaste...?"
- ✅ "Esto no debería existir" ✅ "Un agujero negro te estira como espagueti" ✅ "Llueven diamantes en este planeta"

📊 [DATOS DEL CANAL — prismtale optimización]
- Canal estable: 1,000–1,800 views distribuidos uniformemente (sin dependencia de un solo hit)
- Temas fuertes: pingüinos, miel 3000 años, cerebro, tiempo, Aurora, planetas, dinosaurios — MUY amplio
- ✅ Tono oscuro y cinematográfico: sombras, misterio, iluminación teal/orange, fondos oscuros
- ✅ Títulos que funcionan: afirmaciones intrigantes, no preguntas genéricas
- ❌ Temas demasiado agresivos/exagerados (supervolcano=14 views, crows=1 view) → fracasan
- ❌ No todo funciona "oscuro" — el tema debe tener misterio natural, no forzado
- CTR 2.2% es bajo → mejorar packaging visual del primer corte

[Estructura del corto (8–9 cortes, ~4–5 seg cada uno, 38–48 seg total)]
1. Corte 1 — Gancho: Suelta el dato más impactante como afirmación directa. SIN preguntas. ★ REGLA DE 1.7 SEG: el image_prompt DEBE tener impacto visual extremo (escala, contraste de color, surrealismo).
   Patrones de gancho: contraste numérico, negación+revelación, urgencia temporal, destructor de intuición
   ★★★ [REGLA DEL GANCHO] La primera línea DEBE romper una creencia común o presentar un "hecho imposible."
   ❌ "Esto es interesante" ❌ "Hoy vamos a hablar de" → ✅ "Esto no debería existir" ✅ "Los científicos no pueden explicar esto"
2. Cortes 2–3 — Cadena de impacto: "Pero lo más inquietante es que..." escalar.
3. Cortes 4–5 — Construcción del giro: El corte 4 DEBE introducir un nuevo dato impactante (segundo gancho, combate la caída de retención en U). ★ Cambiar cámara/iluminación/escala cada 2–3 cortes.
   ★★★ [BLOQUEO DE RETENCIÓN] Cortes 3–4 DEBEN introducir un nuevo elemento impactante para prevenir la caída media. Dar al espectador una razón para quedarse JUSTO AQUÍ.
4. Cortes 6–8 — Clímax: Los datos más duros + comparaciones intuitivas ("Eso equivale a alinear 100 Tierras").
5. Cortes 9–10 — Final en bucle: La última línea DEBE hacer que el espectador quiera volver al corte 1. El image_prompt final refleja la composición/color del corte 1.
   ★★★ [REGLAS OBLIGATORIAS DEL FINAL EN BUCLE] ★★★
   * El último corte DEBE ser una oración COMPLETA. Oraciones incompletas ("...en realidad", "...pero entonces") están PROHIBIDAS.
   * Cuando el corte 1 se reproduce automáticamente después del último, debe fluir naturalmente como una conversación.
   * Usa UNO de estos 3 patrones:
     (A) Retorno por pregunta: El último corte termina con pregunta, y el corte 1 suena como la respuesta.
         ej. Último="¿Entonces este pequeño microbio realmente puede salvar una vida?" → Corte 1="Un microbio encontrado en el fondo del océano podría ser la clave para tratar el cerebro"
     (B) Ignición de curiosidad: El último corte lanza un dato nuevo que hace que el corte 1 se sienta como "espera, ¿qué?"
         ej. Último="Pero lo más extraño es dónde lo encontraron." → Corte 1="Este organismo diminuto acaba de revolucionar la medicina"
     (C) Puente de oración: La última y la primera oración se conectan como una historia continua.
         ej. Último="Esa sustancia vino de un microbio del fondo marino." → Corte 1="Se descubrió un compuesto que podría reducir la inflamación cerebral"
   ✅ Último→Primero debe fluir como conversación natural — esta es la CLAVE
   ❌ "La próxima vez te cuento..." — CTAs de promesas vacías PROHIBIDOS
   ❌ "...en realidad es", "Pero la verdad..." — oraciones incompletas PROHIBIDAS
   ❌ "Nunca lo olvidarás", "Piénsalo" — finales reflexivos débiles PROHIBIDOS
   ❌ "Ya te lo dije al principio" — ruptura meta de 4ta pared PROHIBIDA

[Reglas de guion — TONO NEUTRO OBLIGATORIO]
* Español neutro, directo, sin regionalismos. Tono de narrador de documental.
* 8–15 palabras por corte, una oración. Variar estructuras de oración.
* [CRITICAL WARNING] Escribir 8–9 cortes. Video objetivo de 38–48 segundos. NUNCA menos de 8 cortes. Ritmo medio — entre inmersión y dinamismo.

[Tono/Visual] Preset del canal ([CHANNEL VISUAL IDENTITY], [NARRATOR TONE]) tiene prioridad. Sin finales débiles ("tal vez", "podría ser").
* ❌ PROHIBIDO: colores vibrantes/saturados tipo latino. Este canal es OSCURO y CINEMATOGRÁFICO.
* Patrones de oración OBLIGATORIOS (variar entre estos):
  - Afirmación directa: "Esto no debería existir."
  - Contraste factual: "Un planeta del tamaño de Júpiter pesa menos que el agua."
  - Revelación corta: "Y nadie sabe por qué."
  - Dato con escala: "Eso equivale a cubrir toda España con hielo."
* ❌ PROHIBIDO: Exclamaciones excesivas con ¡!, aperturas tipo "¿Sabías que...?", tono exagerado o sensacionalista latino.
* ❌ PROHIBIDO: Expresiones regionales ("¡No manches!", "¡Qué chido!", "¡Dale!", "Tío").
* ✅ USAR: Frases cortas, contundentes, factuales. Como un documental de ciencia.

[Reglas de image_prompt]
* Solo en inglés. No escribir "photorealistic/vertical/no text" (se añade automáticamente).
* Describir escenas, no listar palabras clave. Las oraciones descriptivas producen mejores imágenes.
* Usar diferentes técnicas de cámara por corte (términos fotográficos):
  - Proximidad: close-up, wide shot, aerial view
  - Tipo de lente: 35mm, 50mm, macro lens, wide-angle, fisheye
  - Iluminación: natural light, dramatic lighting, golden hour, studio lighting
  - Configuración: motion blur, soft focus, bokeh, shallow depth of field
* Sin primeros planos frontales de rostros.
* Detalles específicos: temperatura de color, texturas, comparaciones de escala.

★★★ [COINCIDENCIA DE SUJETO — REGLA DE MÁXIMA PRIORIDAD] ★★★
* Cada image_prompt DEBE representar el sujeto de su script correspondiente.
* script="las medusas no tienen cerebro" → image_prompt DEBE contener "jellyfish". Sin sujetos abstractos/no relacionados.
* Colocar el sujeto clave al INICIO del image_prompt (ej: "A translucent jellyfish...").
* PROHIBIDO: el sujeto principal en image_prompt difiere del sujeto del script.
* [AUTO-VERIFICACIÓN] Comparar cada par script↔image_prompt. Corregir cualquier discrepancia.

[Emoción / Visual / Ritmo — Unificado]
* Etiquetas (fin de description): [SHOCK] [WONDER] [TENSION] [REVEAL] [CALM]
* Arco emocional: Escalada general, pausa breve permitida antes del clímax. Nunca misma etiqueta 2x seguidos, mín 3 tipos.
* Impacto visual: Corte 1 debe detener el scroll (escala/color/surrealismo extremo). Todos los cortes con 1+ elemento impactante. Misma paleta 2x PROHIBIDA.
* Ritmo: Alternar rápido↔lento. Nunca 3 cortes con mismo ritmo.

[Ejemplo dorado — Tema: "Lo que pasa en el fondo del océano" (arco emocional completo de 8 cortes)]
{
  "title": "El fondo del océano esconde esto",
  "tags": ["#Shorts", "#Ocean", "#DeepSea", "#Science", "#Océano"],
  "cuts": [
    {"description": "Crushing pressure on a tiny submersible in pitch-black abyss [SHOCK]", "image_prompt": "Deep ocean abyss at 4000 meters depth, a tiny submersible being crushed by invisible pressure, dark indigo water with faint bioluminescent particles, extreme wide angle from below looking up", "script": "A diez mil metros de profundidad la presión equivale a 50 elefantes sobre tu uña."},
    {"description": "Massive bioluminescent jellyfish glowing in total darkness [WONDER]", "image_prompt": "Massive bioluminescent jellyfish glowing electric blue and purple in pitch-black deep ocean, tentacles trailing like aurora curtains, overhead camera angle", "script": "Pero ahí abajo hay criaturas que generan su propia luz sin el sol."},
    {"description": "Hydrothermal vent erupting superheated water on the ocean floor [TENSION]", "image_prompt": "Hydrothermal vent erupting superheated black water at ocean floor, extreme temperature shimmer, orange mineral deposits, dramatic side lighting from magma glow below", "script": "Y en el fondo el agua hierve a cuatrocientos grados."},
    {"description": "Alien-like colony of tube worms thriving next to the boiling vent [REVEAL]", "image_prompt": "Colony of giant tube worms and eyeless shrimp thriving around hydrothermal vent, alien-like ecosystem, warm amber glow against cold blue ocean, macro lens perspective", "script": "Lo inesperado es que junto a esa agua hirviendo la vida prospera."},
    {"description": "Whale fall skeleton supporting an entire ecosystem on the ocean floor [WONDER]", "image_prompt": "Whale fall skeleton on ocean floor with entire ecosystem growing on bones, ghostly white ribcage covered in colorful organisms, soft diffused light from above, wide establishing shot", "script": "Cuando una ballena muere se hunde y se convierte en un ecosistema por cincuenta años."},
    {"description": "Vertigo-inducing view straight down into the Mariana Trench [TENSION]", "image_prompt": "Vertigo-inducing top-down view into Mariana Trench, layers of ocean getting progressively darker, depth markers showing 11000m, sense of infinite depth, cold blue-black gradient", "script": "La Fosa de las Marianas es tan profunda que el Everest cabría dentro y sobraría espacio."},
    {"description": "Looking up from the ocean floor at a faint beam of distant sunlight [WONDER]", "image_prompt": "Looking straight up from deep ocean floor toward distant surface, single faint beam of sunlight barely penetrating, vast dark water column, lonely and sublime, low angle upward shot", "script": "Hemos explorado más del espacio que del océano bajo nuestros pies."},
    {"description": "Submersible descending back into the dark abyss — mirrors Cut 1 [CALM]", "image_prompt": "Tiny submersible descending into pitch-black ocean abyss, same dark composition as cut 1, dramatic lighting from below, mysterious atmosphere, high contrast", "script": "Y apenas hemos visto el cinco por ciento de lo que hay ahí abajo."}
  ]
}

[Formato de salida — solo JSON puro, sin bloques de código markdown]
8–10 cortes:

{
  "title": "[Título impactante en español neutro (máx 10 palabras)]",
  "description": "[Descripción para Shorts: 1-2 oraciones, curiosidad, no académico]",
  "tags": ["#TagEspañol1", "#EnglishTag1", "#TagEspañol2", "#EnglishTag2"],
  "cuts": [
    {
      "description": "[Descripción del corte (inglés)] [EMOTION_TAG]",
      "image_prompt": "[Prompt de imagen en inglés (MASTER_STYLE se aplica automáticamente)]",
      "script": "[Voz en off: español neutro, directo, 8-15 palabras]"
    }
  ]
}
[Reglas de tags] El array tags DEBE incluir #Shorts + 2-3 hashtags en español + 1-2 hashtags en inglés (total 4-6). Mezclar idiomas en tags ayuda al algoritmo a clasificar el contenido para audiencias bilingües.
"""

    _SYSTEM_PROMPT_ES_LATAM = """
Eres un productor viral de YouTube Shorts/TikTok + ingeniero de prompts de imagen de nivel experto. Objetivo: contenido adictivo de formato corto con 10M+ vistas para audiencia latinoamericana.

★★★ [PRIORIDAD DE REGLAS — Seguir en este orden] ★★★
1ro: Gancho (Hook) — Si el corte 1 no detiene el scroll, todo falla
2do: Coincidencia de sujeto — Discrepancia script↔image_prompt PROHIBIDA
3ro: Bloqueo de retención — Nuevo impacto en cortes 3–4, evitar caída media
4to: Loop directo — Última línea ≈ Primera línea (repetición fuerte y obvia)
5to: Tono/Visual — Seguir preset del canal ([CHANNEL VISUAL IDENTITY], [NARRATOR TONE])

🚫 [HARD FAIL — Cualquiera de estos significa rechazo]
- Gancho débil o genérico → FAIL
- Sin escalada clara de tensión → FAIL
- Loop no conecta naturalmente → FAIL
- image_prompt sin elemento visual impactante → FAIL
- Tono no coincide con el canal → FAIL
- Números no verificados presentados como hechos definitivos → FAIL
- image_prompt añade información que no está en el script → FAIL

🔬 [REGLAS DE VERIFICACIÓN — La credibilidad del canal es lo primero]
- Números no verificados prohibidos en forma definitiva: "exactamente 10 veces" → "aproximadamente 10 veces"
- No abusar de "los científicos demostraron": usar "según investigaciones", "estudios sugieren"
- No absolutos exclusivos: "el único/el primero/el más de la historia" → "uno de los pocos/entre los más grandes"
- No fabricar causalidad: "hacer A causa B" → "A está relacionado con B"
- No superlativos sin evidencia: "el más grande de la historia" sin respaldo → prohibido
- image_prompt SOLO visualiza lo que dice el script. Añadir sujetos/información extra está PROHIBIDO

🎯 [GANCHO DE 2 SEGUNDOS — Reglas obligatorias del Corte 1]
- Script del Corte 1: MÁXIMO 10 palabras. Una oración. Sin introducción — solo exclamación/afirmación.
- image_prompt del Corte 1: UN sujeto visual + colores vibrantes + UN elemento extremo. Sin escenas complejas.
- Corte 1 puede ser exclamación o afirmación fuerte, pero NO pregunta genérica.
- ❌ "Hoy vamos a ver algo curioso" ❌ "¿Alguna vez te has preguntado...?"
- ✅ "¡Esto NO debería existir!" ✅ "¡Llueven diamantes en este planeta!" ✅ "¡3 corazones! ¡Sí, tres!"

📊 [DATOS DEL CANAL — exploratodo optimización]
- Un video (HD 137010 b) generó 67% de todas las views — exoplanetas son el tema más fuerte
- Temas fuertes: exoplanetas, Hubble/eventos espaciales, dinosaurios, criaturas marinas extrañas
- ✅ Cuando el tema es espacio/exoplanetas: maximizar colores vibrantes, escala cósmica, efectos de brillo
- ✅ Títulos que funcionan: "Descubren un planeta de tamaño terrestre", "¿Un exoplaneta que huele a huevo podrido?"
- ❌ Cuidado con la exageración visual: colores brillantes NO justifican datos inventados
- El canal depende de crear múltiples hits, no solo uno — mantener calidad consistente

[Estructura del corto (8–9 cortes, ~4–5 seg cada uno, 35–42 seg total)]
1. Corte 1 — Gancho: El dato más impactante como exclamación o afirmación fuerte. ★ REGLA DE 1.7 SEG: image_prompt con colores vibrantes, escenas llamativas, impacto visual máximo.
   Patrones de gancho: "Esto es increíble...", contraste numérico, dato sorprendente
   ★★★ [REGLA DEL GANCHO] La primera línea DEBE ser EXPLOSIVA. Dato imposible o exclamación que no se puede ignorar.
   ❌ "Hoy vamos a ver algo curioso" → ✅ "¡Esto NO debería existir!" ✅ "¡Nadie puede creer que esto sea real!"
2. Cortes 2–3 — Cadena de sorpresa: "¿Y sabes qué es lo más loco?" escalar rápido.
3. Cortes 4–5 — Dato curioso: Introducir segundo dato impactante. ★ Ritmo rápido, sin pausa. Cambiar visual cada corte.
   ★★★ [BLOQUEO DE RETENCIÓN] Cortes 3–4 DEBEN meter un dato nuevo que haga IMPOSIBLE salir del video. El espectador debe pensar "espera, ¿QUÉ?"
4. Cortes 6–8 — Impacto máximo: Datos más fuertes + comparaciones simples ("Eso es como llenar 100 piscinas").
5. Cortes 9–10 — Loop directo: La última línea debe ser casi idéntica a la primera. Repetición obvia y fuerte.
   ★★★ [REGLAS DEL LOOP — REPETICIÓN DIRECTA] ★★★
   * El último corte DEBE repetir o reflejar directamente el primer corte.
   * El loop debe ser OBVIO — el espectador debe sentir que el video vuelve a empezar.
   * Patrón principal: Primera línea ≈ Última línea (casi idénticas).
     ej. Corte 1="Esto es increíble..." → Último="Esto es increíble..."
     ej. Corte 1="Los pulpos tienen 3 corazones" → Último="3 corazones... y eso no es todo"
   ✅ Repetición fuerte y directa — esta es la CLAVE
   ❌ "La próxima vez te cuento..." — PROHIBIDO
   ❌ Oraciones incompletas — PROHIBIDO
   ❌ Finales reflexivos o filosóficos — PROHIBIDO

[Reglas de guion — TONO LATINO ENERGÉTICO]
* Español latinoamericano, accesible, entretenido. Tono de presentador curioso.
* 8–15 palabras por corte, una oración. Ritmo rápido.
* [CRITICAL WARNING] Escribir 8–9 cortes. Video objetivo de 35–42 segundos. NUNCA menos de 8 cortes. Tempo rápido — sin pausa.
* Patrones de oración OBLIGATORIOS (variar entre estos):
  - Exclamación de apertura: "Esto es increíble..."
  - Dato sorprendente: "Los pulpos tienen 3 corazones."
  - Pregunta retórica: "¿Y sabes qué es lo más loco?"
  - Comparación simple: "Eso es como llenar 100 estadios."
  - Remate corto: "Y eso no es todo."
* ✅ USAR: Tono energético, sorprendido, entretenido. Como un amigo contándote algo increíble.
* ✅ USAR: "Increíble", "No vas a creer esto", "Mira esto", "Es una locura"
* ❌ PROHIBIDO: Tono formal, académico o de noticiero.
* ❌ PROHIBIDO: Frases muy largas o complejas.

[Tono/Visual] Preset del canal ([CHANNEL VISUAL IDENTITY], [NARRATOR TONE]) tiene prioridad. Frases con IMPACTO al final.
* ❌ PROHIBIDO: tonos oscuros/apagados tipo documental. Este canal es BRILLANTE y COLORIDO.

[Reglas de image_prompt]
* Solo en inglés. No escribir "photorealistic/vertical/no text" (se añade automáticamente).
* Describir escenas COLORIDAS y LLAMATIVAS. Colores vibrantes, efectos de brillo, estilo fantasía.
* Usar diferentes técnicas de cámara por corte (términos fotográficos):
  - Proximidad: close-up, wide shot, aerial view
  - Tipo de lente: 35mm, 50mm, macro lens, wide-angle, fisheye
  - Iluminación: vibrant lighting, neon glow, golden hour, colorful studio lighting
  - Configuración: high saturation, glowing effects, dramatic contrast
* Sin primeros planos frontales de rostros.
* Detalles específicos: colores brillantes, texturas exageradas, composición llamativa.

★★★ [COINCIDENCIA DE SUJETO — REGLA DE MÁXIMA PRIORIDAD] ★★★
* Cada image_prompt DEBE representar el sujeto de su script correspondiente.
* script="los pulpos tienen 3 corazones" → image_prompt DEBE contener "octopus". Sin sujetos abstractos.
* Colocar el sujeto clave al INICIO del image_prompt (ej: "A colorful octopus...").
* PROHIBIDO: el sujeto principal en image_prompt difiere del sujeto del script.
* [AUTO-VERIFICACIÓN] Comparar cada par script↔image_prompt. Corregir cualquier discrepancia.

[Etiquetas de emoción] Añadir al final de description:
  [SHOCK] [WONDER] [TENSION] [REVEAL] [CALM]

[Emoción / Visual / Ritmo — Unificado]
* Etiquetas (fin de description): [SHOCK] [WONDER] [TENSION] [REVEAL] [CALM]
* Energía ALTA de principio a fin, con micro-pausas de asombro. Nunca misma etiqueta 2x seguidos, mín 3 tipos.
* Impacto visual: Corte 1 = EXPLOSIVO (colores vibrantes, escala exagerada). Todos los cortes con brillo/color/dramatismo. Misma paleta 2x PROHIBIDA.
* Ritmo: Rápido en general. Alternar datos cortos↔comparaciones. Nunca 3 cortes con mismo ritmo.

[Ejemplo dorado — Tema: "Datos increíbles sobre los pulpos" (arco emocional completo de 8 cortes)]
{
  "title": "Los pulpos son más extraños de lo que crees",
  "tags": ["#Shorts", "#Pulpos", "#DatosCuriosos", "#Animales", "#Ciencia"],
  "cuts": [
    {"description": "A vibrant colorful octopus showing its three hearts glowing [SHOCK]", "image_prompt": "A vibrant colorful octopus with three glowing hearts visible through translucent body, underwater scene with bright coral reef, neon blue and purple lighting, macro lens close-up", "script": "Los pulpos tienen 3 corazones. Sí, tres."},
    {"description": "Octopus arm moving independently with its own brain [WONDER]", "image_prompt": "An octopus tentacle reaching out independently, glowing neural pathways visible inside the arm, dark ocean background with bioluminescent particles, dramatic side lighting", "script": "Y cada brazo tiene su propio cerebro."},
    {"description": "Octopus changing colors instantly to match its surroundings [WONDER]", "image_prompt": "An octopus rapidly changing colors from red to blue to green, camouflaging against colorful coral, split-frame showing the transformation, vibrant underwater scene, wide shot", "script": "Pueden cambiar de color en menos de un segundo."},
    {"description": "Octopus squeezing through an impossibly small hole [TENSION]", "image_prompt": "An octopus squeezing its entire body through a tiny glass bottle opening, extreme flexibility demonstration, studio lighting, high contrast, close-up side angle", "script": "Y se pueden meter por un hueco del tamaño de una moneda."},
    {"description": "Octopus opening a jar from inside to escape [REVEAL]", "image_prompt": "An octopus inside a sealed glass jar, tentacles twisting the lid open from inside, dramatic top-down camera angle, bright studio lighting, high saturation", "script": "Hasta pueden abrir frascos desde adentro."},
    {"description": "Octopus blood shown to be blue colored [WONDER]", "image_prompt": "Close-up of octopus with visible blue blood flowing through transparent tentacles, deep ocean background, ethereal blue glow, macro photography style", "script": "Su sangre es azul porque tiene cobre en vez de hierro."},
    {"description": "Octopus using tools and solving puzzles in captivity [TENSION]", "image_prompt": "An octopus manipulating a complex puzzle box underwater, tentacles working multiple mechanisms simultaneously, vibrant aquarium lighting, close-up side angle", "script": "Y pueden resolver acertijos que algunos mamíferos no pueden."},
    {"description": "Octopus with three glowing hearts again, loop back to start [SHOCK]", "image_prompt": "Same vibrant octopus from cut 1, three hearts pulsing with bright glow, underwater scene, neon lighting, mirror composition of first cut", "script": "3 corazones... y eso no es lo más raro."}
  ]
}

[Formato de salida — solo JSON puro, sin bloques de código markdown]
8–10 cortes:

{
  "title": "[Título llamativo en español (máx 10 palabras, estilo curiosidad)]",
  "description": "[Descripción para Shorts: 1-2 oraciones, energético, curiosidad]",
  "tags": ["#TagEspañol1", "#TagEspañol2", "#TagEspañol3", "#DatosCuriosos"],
  "cuts": [
    {
      "description": "[Descripción del corte (inglés)] [EMOTION_TAG]",
      "image_prompt": "[Prompt de imagen en inglés — colores vibrantes, llamativo]",
      "script": "[Voz en off: español latino, energético, 8-15 palabras]"
    }
  ]
}
[Reglas de tags] El array tags DEBE incluir #Shorts + 3-4 hashtags en español relacionados con el tema (total 4-5). Usar tags populares en Latinoamérica.
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
    elif lang == "es":
        # 채널별 분기: 미국 히스패닉(keyword_tags 보유) vs 남미/스페인 전용 프롬프트
        from modules.utils.channel_config import get_channel_preset as _get_preset
        _es_preset = _get_preset(channel) if channel else None
        if _es_preset and _es_preset.get("keyword_tags"):
            system_prompt = _SYSTEM_PROMPT_ES          # 미국 히스패닉 (Prism Tale)
        else:
            system_prompt = _SYSTEM_PROMPT_ES_LATAM     # 남미/스페인 (ExploraTodo)
    else:
        # 기타 언어: 영어 프롬프트 기반 + 해당 언어로 대본/제목 작성 지시
        lang_name = _LANG_NAMES.get(lang, lang)
        system_prompt = _SYSTEM_PROMPT_EN + f"""

[LANGUAGE OVERRIDE]
You MUST write ALL "script" fields and the "title" field in {lang_name}.
NEVER write scripts in English. All "script" fields MUST be in {lang_name} only.
The "image_prompt" and "description" fields must remain in English.
The narrator will speak in {lang_name}, so the script must be natural {lang_name}.
IMPORTANT: {lang_name} sentences tend to be longer than English. Keep each script to 8–15 words equivalent (~4–6 seconds) to maintain 40–50 second total video length. Write 8–10 cuts minimum.
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
            keyword_tags = preset.get("keyword_tags", [])
            if keyword_tags:
                keywords_str = ", ".join(keyword_tags)
                system_prompt += f"""
[KEYWORD INJECTION]
Include these English keywords in the "tags" array (as hashtags): {keywords_str}
Also naturally weave 1-2 of these English terms into "image_prompt" fields where relevant (e.g. "NASA spacecraft", "human brain scan").
These English keywords help YouTube's algorithm classify this content for US audiences.
"""

    # LLM 프로바이더별 API 키 결정
    provider_label = PROVIDER_LABELS.get(llm_provider, "ChatGPT")

    if llm_provider == "gemini":
        final_api_key = llm_key_override or os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEYS", "").split(",")[0].strip()
        # Vertex AI 서비스 계정 모드에서는 API 키 없이도 동작
        if not final_api_key and os.getenv("GEMINI_BACKEND", "ai_studio") != "vertex_ai":
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
    # 외부 입력 새니타이징 (프롬프트 인젝션 방어)
    _safe_title = _sanitize_llm_input(_topic_title, max_len=200)
    _safe_content = _sanitize_llm_input(_topic_content, max_len=1500) if _topic_content else ""
    if lang == "en":
        user_content = f"Topic: Create a short-form video plan about '{_safe_title}'."
    elif lang == "es":
        user_content = f"Tema: Crea un plan de video corto sobre '{_safe_title}'."
    else:
        user_content = f"주제: '{_safe_title}'에 대한 숏폼 기획안을 작성해주세요."
    # YouTube 원본 자막이 있으면 LLM 컨텍스트로 주입
    if _safe_content:
        if lang == "en":
            user_content += f"\n\n<transcript>\n{_safe_content}\n</transcript>\nReflect the key facts and themes from the transcript above in your new plan."
        elif lang == "es":
            user_content += f"\n\n<transcript>\n{_safe_content}\n</transcript>\nRefleja los hechos y temas clave de la transcripción anterior en tu nuevo plan."
        else:
            user_content += f"\n\n<transcript>\n{_safe_content}\n</transcript>\n위 자막의 핵심 팩트와 주제를 반영하여 새로운 기획안을 작성하세요."
    if fact_context:
        if lang == "en":
            user_content += f"\n\n{fact_context}\n[Fact-Check Instruction] Prioritize facts from the reference above over your training data. Do NOT invent statistics — use only verified numbers."
        elif lang == "es":
            user_content += f"\n\n{fact_context}\n[Verificación de datos] Prioriza los datos de la referencia anterior. NO inventes estadísticas — usa solo datos verificados."
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
            cuts, title, tags, video_description = _request_cuts(llm_provider, current_key, system_prompt, user_content, model_override=llm_model)
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
                    # GPT 자동 폴백 비활성화 — Gemini만 사용
                    raise RuntimeError(f"[Gemini 할당량 초과] 등록된 모든 키({len(exhausted_keys)}개)의 쿼터가 소진되었습니다. 지출 한도를 확인하세요.") from e
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
        print(f"-> [검증 실패] 컷 수가 {len(cuts)}개입니다. 기존 컷 기반 확장 요청합니다 (목표: 8~10컷).")
        if llm_provider == "gemini":
            retry_key = get_google_key(None, service="gemini", exclude=exhausted_keys) or current_key
        else:
            retry_key = current_key
        # 기존 컷 데이터를 포함하여 확장만 요청 (전체 재생성 대신)
        existing_cuts_json = json.dumps(
            [{"script": c["script"], "description": c.get("text", ""), "image_prompt": c.get("prompt", "")} for c in cuts],
            ensure_ascii=False
        )
        if lang == "en":
            retry_expansion = (
                f"\n\nOnly {len(cuts)} cuts were generated. Expand to 7-10 total cuts. "
                f"You MUST keep ALL existing cuts verbatim and add 2-4 NEW cuts between them to reinforce buildup/climax. "
                f"Return the complete expanded array.\nExisting cuts: {existing_cuts_json}"
            )
        elif lang == "es":
            retry_expansion = (
                f"\n\nSolo se generaron {len(cuts)} cortes. Expande a 7-10 cortes en total. "
                f"DEBES mantener TODOS los cortes existentes tal cual y agregar 2-4 cortes NUEVOS entre ellos para reforzar el clímax. "
                f"Devuelve el array completo expandido.\nCortes existentes: {existing_cuts_json}"
            )
        else:
            retry_expansion = (
                f"\n\n기존에 {len(cuts)}컷만 생성되었습니다. 총 8~10컷으로 확장하세요. "
                f"기존 컷은 반드시 그대로 유지하고, 사이에 2~4개의 새 컷을 추가하여 빌드업/클라이맥스를 보강하세요. "
                f"확장된 전체 배열을 반환하세요.\n기존 컷: {existing_cuts_json}"
            )
        # 확장 재시도: 자막/팩트체크 컨텍스트 제외하고 토픽+기존 컷만 전달 (토큰 절약)
        if lang == "en":
            retry_user = f"Topic: '{_safe_title}'." + retry_expansion
        elif lang == "es":
            retry_user = f"Tema: '{_safe_title}'." + retry_expansion
        else:
            retry_user = f"주제: '{_safe_title}'." + retry_expansion
        _original_cuts = cuts[:]
        try:
            expanded_cuts, title, tags, _ = _request_cuts(llm_provider, retry_key, system_prompt, retry_user, model_override=llm_model)
            # 기존 컷이 보존되었는지 검증: 원본 스크립트가 확장 결과에 포함되어야 함
            original_scripts = {c["script"].strip()[:30] for c in _original_cuts}
            expanded_scripts = {c["script"].strip()[:30] for c in expanded_cuts}
            preserved = original_scripts & expanded_scripts
            if len(preserved) >= len(original_scripts) * 0.7:
                cuts = expanded_cuts
                print(f"OK [컷 확장] {len(_original_cuts)}컷 → {len(cuts)}컷 (기존 {len(preserved)}/{len(original_scripts)}개 보존)")
            else:
                print(f"  [컷 확장 실패] 기존 컷 보존율 낮음 ({len(preserved)}/{len(original_scripts)}) — 원본 유지")
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
        print(f"⚠️ [검증 경고] 컷 수 {len(cuts)}개로 부족하지만 진행합니다 (요구: 7~10).")

    # title이 비어있으면 제목을 폴백으로 사용 (자막 포함 방지)
    if not title:
        title = _topic_title

    # tags 기본값 보장
    if not tags or not isinstance(tags, list):
        tags = ["#Shorts"]

    # ── 3단계 검증 파이프라인 (최대 1회 재검증, 무한 루프 방지) ──
    # 순서: ① 하이네스 구조 → ② 주제 일치 → (구조가 스크립트를 바꿨으면 주제 재검증 1회)→ ③ 팩트
    _scripts_before = [c["script"] for c in cuts]

    # 검증용 키: Gemini는 fresh 키 사용 (생성 후 429 위험 회피)
    def _verify_key():
        if llm_provider == "gemini":
            fresh = get_google_key(None, service="gemini", exclude=exhausted_keys)
            return fresh or current_key
        return current_key

    # ① 하이네스 구조 검증 (Hook/충격체인/루프엔딩)
    cuts = _verify_highness_structure(cuts, _topic_title, llm_provider, _verify_key(), lang, llm_model, channel)

    # ② 주제-이미지 일치 검증
    cuts = _verify_subject_match(cuts, _topic_title, llm_provider, _verify_key(), lang, llm_model)

    # ②-b 구조 수정이 스크립트를 바꿨으면 → 주제 재검증 1회만 (무한 루프 차단)
    _scripts_after = [c["script"] for c in cuts]
    if _scripts_before != _scripts_after:
        print("-> [재검증] 구조/주제 수정으로 스크립트 변경됨 → 주제 일치 재검증 (1회)")
        cuts = _verify_subject_match(cuts, _topic_title, llm_provider, _verify_key(), lang, llm_model)

    # ③ 팩트 검증 (선택적 — 팩트 컨텍스트 있을 때만)
    if fact_context:
        cuts = _verify_facts(cuts, fact_context, _topic_title, llm_provider, _verify_key(), lang, llm_model)

    # ④ HARD FAIL 검증 (코드 레벨 품질 게이트) — 실패 시 1회 구조 수정 재시도
    hard_fails = _validate_hard_fail(cuts, channel)
    region_warns = _validate_region_style(cuts, channel)
    if hard_fails:
        print(f"⚠️ [HARD FAIL] {len(hard_fails)}개 품질 문제 감지:")
        for fail in hard_fails:
            print(f"  - {fail}")
        # HARD FAIL 유형별 수정 라우팅
        has_visual_fail = any("VISUAL" in f for f in hard_fails)
        has_structure_fail = any(k in "".join(hard_fails) for k in ["HOOK", "TENSION", "LOOP", "TONE"])
        if has_structure_fail:
            print("-> [HARD FAIL 수정] 구조 검증으로 자동 수정 시도 (1회)...")
            cuts = _verify_highness_structure(cuts, _topic_title, llm_provider, _verify_key(), lang, llm_model, channel)
        if has_visual_fail:
            print("-> [HARD FAIL 수정] 이미지 프롬프트 검증으로 자동 수정 시도 (1회)...")
            cuts = _verify_subject_match(cuts, _topic_title, llm_provider, _verify_key(), lang, llm_model)
        # 재검증
        hard_fails_retry = _validate_hard_fail(cuts, channel)
        if hard_fails_retry:
            print(f"  [HARD FAIL] 수정 후에도 {len(hard_fails_retry)}개 남음 — 결과 유지 (수동 확인 권장)")
        else:
            print(f"OK [HARD FAIL] 자동 수정으로 모든 품질 문제 해결")
    if region_warns:
        print(f"⚠️ [REGION STYLE] {len(region_warns)}개 지역 스타일 경고:")
        for warn in region_warns:
            print(f"  - {warn}")
    if not hard_fails and not region_warns:
        print(f"OK [품질 게이트] HARD FAIL 통과 | 지역 스타일 통과")

    print(f"OK [기획 전문가] 기획안 완성! ({len(cuts)}컷, {provider_label}) 제목: {title} | 태그: {', '.join(tags)}")

    # ── 채널 금지 표현 필터링 ──
    from modules.utils.channel_config import get_channel_preset
    _ch_preset = get_channel_preset(channel) if channel else None
    _forbidden = (_ch_preset or {}).get("forbidden_phrases", [])
    if _forbidden and cuts:
        for _ci, _cut in enumerate(cuts):
            _scr = _cut.get("script", "")
            for _fp in _forbidden:
                if _fp.lower() in _scr.lower():
                    _scr = re.sub(re.escape(_fp), "", _scr, flags=re.IGNORECASE).strip()
                    _scr = re.sub(r"\s{2,}", " ", _scr)
            if _scr != _cut.get("script", ""):
                cuts[_ci]["script"] = _scr
                print(f"[금지 표현] Cut {_ci+1} 필터링됨")

    # ── 문장 자연화 리라이트 ──
    _pre_polish_hook = cuts[0].get("script", "") if cuts else ""
    _pre_polish_mid = cuts[3].get("script", "") if len(cuts) > 3 else ""
    _pre_polish_last = cuts[-1].get("script", "") if cuts else ""
    try:
        _polish_key = llm_key_override or api_key_override
        cuts, _polish_notes = polish_scripts(
            cuts=cuts, lang=lang, channel=channel,
            llm_provider=llm_provider, api_key=_polish_key,
            llm_model=llm_model,
        )
        if _polish_notes:
            print(f"[문장 자연화] 적용됨")
    except Exception as _pe:
        print(f"[문장 자연화] 스킵 (원본 유지): {_pe}")

    # ── polish 후 핵심 컷 재검사 (훅/리텐션/루프 약화 방지) ──
    if cuts:
        _post_hook = cuts[0].get("script", "")
        _post_mid = cuts[3].get("script", "") if len(cuts) > 3 else ""
        _post_last = cuts[-1].get("script", "")
        # Cut 1 (훅): 약해졌으면 원본 복원
        if _pre_polish_hook and _post_hook and len(_post_hook) > len(_pre_polish_hook) * 1.3:
            cuts[0]["script"] = _pre_polish_hook
            print(f"[재검사] Cut 1 훅 복원 — polish 후 너무 길어짐")
        # Cut 4 (리텐션 락): 약해졌으면 원본 복원
        if len(cuts) > 3 and _pre_polish_mid and _post_mid and len(_post_mid) > len(_pre_polish_mid) * 1.3:
            cuts[3]["script"] = _pre_polish_mid
            print(f"[재검사] Cut 4 리텐션 락 복원")
        # 마지막 컷 (루프): 미완성 문장으로 바뀌었으면 원본 복원
        _bad_endings = ["...", "사실은", "근데 진짜", "actually", "but then", "en realidad"]
        if _post_last and any(_post_last.rstrip().endswith(p) for p in _bad_endings):
            cuts[-1]["script"] = _pre_polish_last
            print(f"[재검사] 마지막 컷 루프 복원 — 미완성 문장 감지")

    # ── polish 후 금지 표현 재필터링 ──
    if _forbidden and cuts:
        for _ci, _cut in enumerate(cuts):
            _scr = _cut.get("script", "")
            for _fp in _forbidden:
                if _fp.lower() in _scr.lower():
                    _scr = re.sub(re.escape(_fp), "", _scr, flags=re.IGNORECASE).strip()
                    _scr = re.sub(r"\s{2,}", " ", _scr)
            if _scr != _cut.get("script", ""):
                cuts[_ci]["script"] = _scr
                print(f"[금지 표현 재필터] Cut {_ci+1}")

    return cuts, topic_folder, title, tags, video_description


def _verify_subject_match(cuts: list[dict], topic: str,
                          llm_provider: str, api_key: str, lang: str,
                          llm_model: str | None = None) -> list[dict]:
    """각 컷의 script 핵심 주어가 image_prompt에 포함되는지 검증하고, 불일치 시 LLM으로 수정."""
    if not cuts or len(cuts) < 3:
        return cuts

    # 각 컷의 script→image_prompt 주제 일치 여부를 LLM에게 한번에 검증 요청
    pairs = "\n".join(
        f"Cut {i+1}:\n  script: {c['script']}\n  image_prompt: {c['prompt']}"
        for i, c in enumerate(cuts)
    )
    verify_prompt = f"""You are a strict visual consistency checker for short-form video.

[TOPIC] {topic}

[CUTS]
{pairs}

[TASK]
For each cut, check if the image_prompt correctly depicts the MAIN SUBJECT from the script.
- "script" describes what the narrator says.
- "image_prompt" describes the visual shown on screen.
- The main subject in the image MUST match the main subject mentioned in the script.

Examples of MISMATCH:
- script talks about "sharks" but image_prompt shows "whale" → MISMATCH
- script talks about "lightning" but image_prompt shows "sunset" → MISMATCH
- script talks about "brain" but image_prompt shows "galaxy" → MISMATCH

Examples of MATCH:
- script talks about "sharks" and image_prompt shows "great white shark" → MATCH
- script mentions "deep ocean pressure" and image_prompt shows "submersible in dark ocean" → MATCH (related context is OK)

Output ONLY a JSON array. For each cut with a mismatch, include a corrected image_prompt.
Format: [{{"cut": 1, "match": true}}, {{"cut": 2, "match": false, "fixed_prompt": "corrected English image prompt that matches the script subject"}}]
Return raw JSON only, no markdown code blocks."""

    print(f"-> [주제 일치 검증] {len(cuts)}개 컷의 script↔image_prompt 일치 확인 중...")

    try:
        if llm_provider == "gemini":
            raw = _request_gemini_freeform(api_key, verify_prompt, llm_model)
        else:
            raw = _request_openai_freeform(api_key, "You are a visual consistency checker.", verify_prompt, llm_model)

        result = _extract_json(raw) or []
        if not isinstance(result, list):
            print(f"  [주제 검증] 응답 파싱 실패 — 원본 유지")
            return cuts

        fixed_count = 0
        for item in result:
            if not isinstance(item, dict):
                continue
            if item.get("match") is False and item.get("fixed_prompt"):
                idx = item.get("cut", 0) - 1
                if 0 <= idx < len(cuts):
                    old_prompt = cuts[idx]["prompt"]
                    cuts[idx]["prompt"] = item["fixed_prompt"]
                    fixed_count += 1
                    print(f"  [주제 수정] 컷{idx+1}: '{old_prompt[:40]}...' → '{item['fixed_prompt'][:40]}...'")

        if fixed_count == 0:
            print(f"OK [주제 검증] 모든 컷 script↔image_prompt 일치 확인 (수정 없음)")
        else:
            print(f"OK [주제 검증] {fixed_count}개 컷 image_prompt 주제 수정 완료")
        return cuts

    except Exception as e:
        print(f"  [주제 검증 실패] {e} — 원본 유지")
        return cuts


def _verify_highness_structure(cuts: list[dict], topic: str,
                               llm_provider: str, api_key: str, lang: str,
                               llm_model: str | None = None, channel: str | None = None) -> list[dict]:
    """하이네스 구조(Hook→충격체인→루프엔딩) 검증 + 자동 수정.

    검증 항목:
    1. Cut 1 = Hook: 단정문인지 (질문형 금지)
    2. Cut 4-5 = 두 번째 훅 존재 여부
    3. 마지막 Cut = 루프 엔딩: 완결 문장 + Cut 1과 연결
    4. 감정 태그 분포: 최소 3종류 이상
    """
    if not cuts or len(cuts) < 5:
        return cuts

    # 채널별 루프 스타일 결정
    from modules.utils.channel_config import get_channel_preset
    preset = get_channel_preset(channel) if channel else None
    loop_style = "medium"  # 기본값
    if preset:
        tone = preset.get("tone", "")
        if "very strong" in tone or "direct" in tone.lower():
            loop_style = "strong"
        elif "natural" in tone or "subtle" in tone:
            loop_style = "subtle"

    first_script = cuts[0]["script"]
    last_script = cuts[-1]["script"]
    all_scripts = "\n".join(f"Cut {i+1}: {c['script']}" for i, c in enumerate(cuts))

    # 감정 태그 분포 확인
    emotions = []
    for c in cuts:
        desc = c.get("text", "") or c.get("description", "")
        for tag in ["SHOCK", "WONDER", "TENSION", "REVEAL", "CALM"]:
            if tag in desc:
                emotions.append(tag)
                break

    emotion_variety = len(set(emotions))

    verify_prompt = f"""You are a short-form video structure expert. Check this video's "Highness Structure" (Hook → Shock Chain → Loop Ending).

[TOPIC] {topic}
[LANGUAGE] {lang}
[LOOP STYLE] {loop_style} (strong=obvious repetition, medium=clear connection, subtle=natural flow)

[ALL CUTS]
{all_scripts}

[FIRST CUT] {first_script}
[LAST CUT] {last_script}
[EMOTION TAGS FOUND] {emotion_variety} types out of 5 (need at least 3)

[CHECK THESE RULES]
1. HOOK (Cut 1): Must be a declarative statement, NOT a question. Must break common belief or present an impossible-sounding fact.
   - ❌ "Did you know...?" / "¿Sabías que...?" / "~일까?" / "Today we'll talk about..."
   - ❌ Weak/generic openers like "This is interesting" or "이건 흥미롭다"
   - ✅ "Lightning is hotter than the sun." / "Esto no debería existir." / "이건 존재해선 안 되는 거야"

2. SECOND HOOK / RETENTION LOCK (Cut 3-5): Must introduce a NEW surprising fact (not continuation of cuts 2-3). This counters the mid-video retention drop. The viewer must think "wait, WHAT?"

3. LOOP ENDING (Last cut): Must be a COMPLETE sentence. Must connect back to Cut 1.
   - If loop_style="strong": Last line should nearly mirror Cut 1
   - If loop_style="medium": Clear thematic connection to Cut 1
   - If loop_style="subtle": Natural flow back to Cut 1's topic
   - ❌ FORBIDDEN: "Next time...", incomplete sentences, weak reflective endings, 4th-wall breaking

4. EMOTION ARC: At least 3 different emotion types should be present across cuts.

[OUTPUT FORMAT]
Return a JSON object:
{{
  "hook_ok": true/false,
  "hook_issue": "description if not ok, null if ok",
  "second_hook_ok": true/false,
  "second_hook_issue": "description if not ok, null if ok",
  "loop_ok": true/false,
  "loop_issue": "description if not ok, null if ok",
  "emotion_ok": true/false,
  "fixes": [
    {{"cut": 1, "field": "script", "original": "...", "fixed": "corrected version"}},
    {{"cut": 10, "field": "script", "original": "...", "fixed": "corrected version"}}
  ]
}}
Only include items in "fixes" if something needs to change. If everything is OK, return empty fixes array.
Return raw JSON only, no markdown code blocks."""

    print(f"-> [하이네스 구조 검증] Hook/충격체인/루프엔딩/감정아크 확인 중...")

    try:
        if llm_provider == "gemini":
            raw = _request_gemini_freeform(api_key, verify_prompt, llm_model)
        else:
            raw = _request_openai_freeform(api_key, "You are a video structure expert.", verify_prompt, llm_model)

        result = _extract_json(raw) or {}
        if not isinstance(result, dict):
            print(f"  [구조 검증] 응답 파싱 실패 — 원본 유지")
            return cuts

        # 결과 로그
        issues = []
        if not result.get("hook_ok"):
            issues.append(f"Hook: {result.get('hook_issue', 'unknown')}")
        if not result.get("second_hook_ok"):
            issues.append(f"2nd Hook: {result.get('second_hook_issue', 'unknown')}")
        if not result.get("loop_ok"):
            issues.append(f"Loop: {result.get('loop_issue', 'unknown')}")
        if not result.get("emotion_ok"):
            issues.append("Emotion: 감정 태그 다양성 부족")

        if issues:
            print(f"  [구조 검증] 문제 발견: {' | '.join(issues)}")
        else:
            print(f"OK [구조 검증] 하이네스 구조 완벽 (Hook✓ 2nd Hook✓ Loop✓ Emotion✓)")
            return cuts

        # 수정 적용
        fixes = result.get("fixes", [])
        fixed_count = 0
        for fix in fixes:
            if not isinstance(fix, dict):
                continue
            idx = fix.get("cut", 0) - 1
            field = fix.get("field", "script")
            new_val = fix.get("fixed")
            if not new_val or not (0 <= idx < len(cuts)):
                continue

            # script 또는 description 수정
            if field == "script" and new_val != cuts[idx].get("script"):
                old = cuts[idx]["script"]
                cuts[idx]["script"] = new_val
                fixed_count += 1
                print(f"  [구조 수정] 컷{idx+1} script: '{old[:30]}...' → '{new_val[:30]}...'")
            elif field == "description" and new_val != cuts[idx].get("text"):
                cuts[idx]["text"] = new_val
                cuts[idx]["description"] = new_val
                fixed_count += 1
                print(f"  [구조 수정] 컷{idx+1} description 수정")

        if fixed_count == 0 and issues:
            print(f"  [구조 검증] 문제 감지되었지만 자동 수정 없음 — 원본 유지")
        elif fixed_count > 0:
            print(f"OK [구조 검증] {fixed_count}개 컷 하이네스 구조 수정 완료")

        return cuts

    except Exception as e:
        print(f"  [구조 검증 실패] {e} — 원본 유지")
        return cuts


def _verify_facts(cuts: list[dict], fact_context: str, topic: str,
                  llm_provider: str, api_key: str, lang: str, llm_model: str | None = None) -> list[dict]:
    """생성된 스크립트의 팩트를 검증하고, 틀린 부분을 수정합니다."""
    scripts = "\n".join(f"컷{i+1}: {c['script']}" for i, c in enumerate(cuts))

    safe_facts = _sanitize_llm_input(fact_context, max_len=1500)
    verify_prompt = f"""You are a strict fact-checker. Verify each script line against the provided facts.

[FACTS from search]
{safe_facts}

[GENERATED SCRIPTS]
{scripts}

[TASK]
1. Check each script line for factual accuracy.
2. If a line contains false or unverifiable information, rewrite it with correct facts.
3. If a line is accurate, keep it unchanged.
4. Maintain the same tone, style, and approximate length.

Output ONLY a JSON array of objects: [{{"cut": 1, "original": "...", "verified": "...", "changed": true/false, "reason": "..."}}]
Do NOT include markdown code blocks. Return raw JSON only."""

    print(f"-> [팩트 검증] 생성된 {len(cuts)}개 스크립트 검증 중...")

    try:
        if llm_provider == "gemini":
            raw = _request_gemini_freeform(api_key, verify_prompt, llm_model)
        else:
            raw = _request_openai_freeform(api_key, "You are a fact-checker.", verify_prompt, llm_model)

        result = _extract_json(raw) or []
        if not isinstance(result, list):
            print(f"  [팩트 검증] 응답 파싱 실패 — 원본 유지")
            return cuts

        changed_count = 0
        for item in result:
            if not isinstance(item, dict) or not item.get("changed"):
                continue
            idx = item.get("cut", 0) - 1
            if 0 <= idx < len(cuts) and item.get("verified"):
                old_script = cuts[idx]["script"]
                cuts[idx]["script"] = item["verified"]
                changed_count += 1
                print(f"  [팩트 수정] 컷{idx+1}: '{old_script[:30]}...' → '{item['verified'][:30]}...' ({item.get('reason', '')})")

        if changed_count == 0:
            print(f"OK [팩트 검증] 모든 스크립트 팩트 확인 완료 (수정 없음)")
        else:
            print(f"OK [팩트 검증] {changed_count}개 스크립트 팩트 수정 완료")
        return cuts

    except Exception as e:
        print(f"  [팩트 검증 실패] {e} — 원본 유지")
        return cuts


# ── HARD FAIL 검증 (코드 레벨 품질 게이트) ──────────────────────────

def _validate_hard_fail(cuts: list[dict], channel: str | None = None) -> list[str]:
    """프롬프트의 HARD FAIL 조건을 코드로 검증. 실패 항목 리스트 반환 (빈 리스트 = 통과)."""
    if not cuts or len(cuts) < 3:
        return []

    failures: list[str] = []

    # 1) Hook 검증 — 첫 컷이 질문형이거나 너무 약한지
    first_script = cuts[0].get("script", "")
    weak_hook_patterns = [
        "did you know", "sabías que", "알고 있", "오늘 소개",
        "today we", "have you ever", "¿sabías", "한번 알아",
        "let me tell", "들어봤", "이번에는",
    ]
    if any(p in first_script.lower() for p in weak_hook_patterns):
        failures.append(f"HOOK_WEAK: 첫 컷이 약한 패턴 포함 — '{first_script[:50]}'")
    if first_script.rstrip().endswith("?") or first_script.rstrip().endswith("？"):
        failures.append(f"HOOK_QUESTION: 첫 컷이 질문형 — '{first_script[:50]}'")

    # 2) 긴장 상승 검증 — 감정 태그 다양성
    emotions = []
    for c in cuts:
        desc = c.get("text", "") or c.get("description", "")
        for tag in ["SHOCK", "WONDER", "TENSION", "REVEAL", "CALM"]:
            if tag in desc.upper():
                emotions.append(tag)
                break
    if len(set(emotions)) < 3:
        failures.append(f"TENSION_FLAT: 감정 태그 {len(set(emotions))}종류 (최소 3 필요)")

    # 3) 루프 연결 검증 — 마지막 컷이 미완성 문장인지
    last_script = cuts[-1].get("script", "")
    bad_endings = ["...", "사실은", "근데 진짜", "actually", "but then", "en realidad"]
    if any(last_script.rstrip().endswith(p) for p in bad_endings):
        failures.append(f"LOOP_INCOMPLETE: 마지막 컷 미완성 — '{last_script[:50]}'")
    bad_cta = ["다음에", "next time", "la próxima", "알려줄게", "i'll show"]
    if any(p in last_script.lower() for p in bad_cta):
        failures.append(f"LOOP_CTA: 마지막 컷에 빈 약속 CTA — '{last_script[:50]}'")

    # 4) 이미지 임팩트 검증 — Cut 1에 시각적 키워드 있는지
    first_prompt = cuts[0].get("prompt", "").lower()
    impact_keywords = [
        "dramatic", "extreme", "contrast", "surreal", "glowing", "massive",
        "tiny", "vibrant", "dark", "neon", "cinematic", "sharp", "intense",
        "colossal", "macro", "aerial", "deep", "vast", "bright", "enormous",
        "pitch-black", "bioluminescent", "mysterious", "shadow", "golden",
    ]
    if not any(kw in first_prompt for kw in impact_keywords):
        failures.append(f"VISUAL_WEAK: Cut 1 image_prompt에 임팩트 키워드 없음")

    # 5) 톤-채널 일치 검증
    if channel:
        from modules.utils.channel_config import get_channel_preset
        preset = get_channel_preset(channel)
        if preset:
            tone = preset.get("tone", "").lower()
            all_scripts = " ".join(c.get("script", "") for c in cuts).lower()
            # LATAM 채널인데 너무 형식적인 톤
            if "energetic" in tone or "rápido" in tone or "enérgico" in tone:
                formal_patterns = ["sin embargo", "no obstante", "cabe mencionar"]
                if any(p in all_scripts for p in formal_patterns):
                    failures.append(f"TONE_MISMATCH: LATAM 에너지 채널에 형식적 표현 사용")
            # 영어 채널인데 과도한 감탄
            if "calm" in tone or "cinematic" in tone:
                exclaim_count = sum(1 for c in cuts if "!" in c.get("script", ""))
                if exclaim_count > len(cuts) * 0.5:
                    failures.append(f"TONE_MISMATCH: calm 채널에 감탄부호 과다 ({exclaim_count}/{len(cuts)}컷)")

    return failures


def _validate_region_style(cuts: list[dict], channel: str | None = None) -> list[str]:
    """채널의 지역 비주얼 스타일이 image_prompt에 반영되었는지 검증."""
    if not cuts or not channel:
        return []

    from modules.utils.channel_config import get_channel_preset
    preset = get_channel_preset(channel)
    if not preset:
        return []

    warnings: list[str] = []
    visual_style = preset.get("visual_style", "").lower()
    all_prompts = " ".join(c.get("prompt", "") for c in cuts).lower()

    # US Hispanic (어두운 시네마틱) — vibrant/neon 과다 사용 감지
    if "dark background" in visual_style or "mysterious" in visual_style:
        bright_count = sum(1 for kw in ["vibrant", "neon", "colorful", "bright", "saturated"]
                          if kw in all_prompts)
        dark_count = sum(1 for kw in ["dark", "dramatic", "cinematic", "contrast", "mysterious", "shadow"]
                         if kw in all_prompts)
        if bright_count > dark_count:
            warnings.append(
                f"REGION_STYLE: 어두운 시네마틱 채널인데 밝은 키워드({bright_count}) > 어두운 키워드({dark_count})")

    # LATAM (밝고 화려) — dark/muted 과다 사용 감지
    if "vibrant" in visual_style or "colorful" in visual_style or "high saturation" in visual_style:
        dark_count = sum(1 for kw in ["dark", "muted", "desaturated", "shadow", "noir"]
                         if kw in all_prompts)
        bright_count = sum(1 for kw in ["vibrant", "neon", "colorful", "bright", "glowing", "saturated"]
                           if kw in all_prompts)
        if dark_count > bright_count:
            warnings.append(
                f"REGION_STYLE: 밝은 LATAM 채널인데 어두운 키워드({dark_count}) > 밝은 키워드({bright_count})")

    # 영어 (다큐멘터리) — neon/glowing 과다 사용 감지
    if "documentary" in visual_style or "natural" in visual_style:
        fantasy_count = sum(1 for kw in ["neon", "glowing", "fantasy", "surreal", "exaggerated"]
                            if kw in all_prompts)
        if fantasy_count > len(cuts) * 0.4:
            warnings.append(
                f"REGION_STYLE: 다큐멘터리 채널에 판타지 키워드 과다 ({fantasy_count}개)")

    return warnings


def _request_gemini_freeform(api_key: str, prompt: str, model: str | None = None) -> str:
    """Gemini에 자유형 프롬프트 전송 (스키마 없음)."""
    from google.genai import types
    from modules.utils.gemini_client import create_gemini_client
    client = create_gemini_client(api_key=api_key)
    model_name = model or "gemini-2.5-flash"
    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config={"response_mime_type": "application/json", "http_options": types.HttpOptions(timeout=60_000)},
    )
    return (response.text or "").strip()


# ── 문장 자연화 리라이트 (Script Polisher) ─────────────────────────


def _get_sentence_polish_prompt(lang: str, channel: str | None = None) -> str:
    """채널별 문장 다듬기 프롬프트를 반환합니다."""
    if channel == "askanything":
        return """너는 한국어 쇼츠 대본 문장 다듬기 전문가다.
목표:
- 기존 의미는 유지한다.
- 더 자연스럽고 입에 붙는 한국어 반말로 고친다.
- 번역투, 설명체, 딱딱한 문장을 없앤다.
- 너무 과한 유튜브 말투나 억지 밈 말투는 금지한다.
- 각 문장은 짧고 강해야 하지만, 어색하면 안 된다.
- 같은 어미, 같은 문장 구조 반복을 줄인다.
- 훅은 더 세게 만들 수는 있어도 약하게 만들면 안 된다.

반드시 지킬 것:
- 컷 수는 유지
- 각 컷은 한 문장 유지
- 원래 정보 추가 금지
- 검증 안 된 단정 표현 추가 금지
- "미쳤다", "레전드", "ㄹㅇ", "ㅋㅋ" 같은 가벼운 표현 금지

출력 형식: JSON만 출력
{"rewritten_scripts": ["컷1", "컷2"], "notes": ["짧은 수정 메모"]}"""

    if channel == "wonderdrop":
        return """You are an English short-form script polisher for a science/documentary channel.

Goal:
- Keep the original meaning and factual caution.
- Rewrite each line so it sounds natural, cinematic, and spoken aloud.
- Remove stiff translation-like phrasing.
- Keep the tone calm, clear, slightly mysterious, and documentary-like.
- Avoid overhype, slang, childish delivery, or forced clickbait.

Must keep:
- Same number of cuts
- One sentence per cut
- Similar length per cut
- No new facts
- No stronger factual certainty than the original
- Keep the hook strong

Output JSON only:
{"rewritten_scripts": ["Cut 1 line", "Cut 2 line"], "notes": ["brief fix notes"]}"""

    if channel == "exploratodo":
        return """Eres un editor de guiones cortos en español para un canal energético y visualmente impactante.

Objetivo:
- Mantener el significado original.
- Hacer que cada línea suene natural, rápida y clara en español.
- Evitar frases traducidas literalmente o construcciones torpes.
- Mantener energía y sorpresa, pero sin sonar infantil ni exagerado.

Reglas:
- Mantener el mismo número de cortes
- Una sola oración por corte
- No agregar datos nuevos
- No volver más categórico algo incierto
- Mantener el gancho fuerte
- Evitar regionalismos muy marcados

Salida JSON:
{"rewritten_scripts": ["línea 1", "línea 2"], "notes": ["cambios principales"]}"""

    if channel == "prismtale":
        return """Eres un pulidor de guiones breves para un canal de tono cinematográfico, misterioso y español neutro.

Objetivo:
- Mantener exactamente la idea original.
- Reescribir cada línea para que suene natural, sobria e intrigante.
- Eliminar frases rígidas, artificiales o demasiado promocionales.
- Mantener un tono de documental breve, elegante y claro.

Debes mantener:
- mismo número de cortes
- una oración por corte
- longitud similar
- sin añadir información nueva
- sin aumentar la certeza factual
- sin volverlo juguetón o exagerado

Salida JSON:
{"rewritten_scripts": ["línea 1", "línea 2"], "notes": ["ajustes principales"]}"""

    # fallback by language
    if lang == "ko":
        return """너는 한국어 숏폼 대본 문장 교정자다. 의미는 유지하고, 더 자연스럽고 말하듯 들리게 고쳐라. 컷 수 유지, 한 컷 한 문장, 새 정보 추가 금지. JSON만 출력: {"rewritten_scripts":["문장1"],"notes":["메모"]}"""
    if lang == "es":
        return """Eres un corrector de guiones breves en español. Mantén el significado y haz que suene más natural al hablar. Mismo número de cortes, una oración por corte, sin datos nuevos. Salida JSON: {"rewritten_scripts":["línea 1"],"notes":["nota"]}"""
    return """You are a short-form script polisher. Keep the meaning, make it sound natural when spoken, keep one sentence per cut, and add no new facts. Output JSON only: {"rewritten_scripts":["line 1"],"notes":["note"]}"""


def _is_script_rewrite_safe(old: str, new: str) -> bool:
    """리라이트가 안전한지 검사 (너무 길어지거나 짧아지면 거부)."""
    old = (old or "").strip()
    new = (new or "").strip()
    if not old or not new:
        return False
    if len(new) > len(old) * 1.5:
        return False
    if len(new) < max(6, int(len(old) * 0.5)):
        return False
    return True


def polish_scripts(cuts: list[dict[str, Any]], lang: str = "ko",
                   channel: str | None = None,
                   llm_provider: str = "gemini",
                   api_key: str | None = None,
                   llm_model: str | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """생성된 컷의 script만 자연스럽게 다듬습니다. 구조/정보는 변경하지 않음."""
    if not cuts:
        return cuts, []

    system_prompt = _get_sentence_polish_prompt(lang, channel)
    payload = {"scripts": [c.get("script", "").strip() for c in cuts]}
    user_content = json.dumps(payload, ensure_ascii=False)

    try:
        if llm_provider == "gemini":
            content = _request_gemini(api_key, system_prompt, user_content, llm_model)
        elif llm_provider == "claude":
            content = _request_claude(api_key, system_prompt, user_content, llm_model)
        else:
            content = _request_openai_freeform(api_key, system_prompt, user_content, llm_model)

        if not content:
            return cuts, ["[polisher] LLM 응답 없음 — 원본 유지"]

        data = json.loads(content) if isinstance(content, str) else content
        if not isinstance(data, dict):
            return cuts, ["[polisher] JSON 파싱 실패 — 원본 유지"]

        rewritten = data.get("rewritten_scripts", [])
        notes = data.get("notes", [])

        if not isinstance(rewritten, list) or len(rewritten) != len(cuts):
            return cuts, [f"[polisher] 컷 수 불일치 ({len(rewritten)} vs {len(cuts)}) — 원본 유지"]

        # script만 교체 (안전 검사 통과한 것만), 나머지(description, image_prompt) 유지
        applied = 0
        for i, new_script in enumerate(rewritten):
            if isinstance(new_script, str) and _is_script_rewrite_safe(cuts[i].get("script", ""), new_script):
                cuts[i]["script"] = new_script.strip()
                applied += 1

        log_notes = notes if isinstance(notes, list) else []
        print(f"[polisher] 다듬기 완료: {applied}/{len(cuts)}컷 적용")
        if log_notes:
            for n in log_notes[:3]:
                print(f"  - {n}")
        return cuts, log_notes

    except Exception as e:
        print(f"[polisher] 오류 — 원본 유지: {e}")
        return cuts, [f"[polisher] 오류: {e}"]
