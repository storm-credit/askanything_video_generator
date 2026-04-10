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


_VALID_EMOTIONS = {"[SHOCK]", "[WONDER]", "[TENSION]", "[REVEAL]", "[URGENCY]", "[DISBELIEF]", "[IDENTITY]", "[CALM]"}

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


_last_gemini_request_time = 0.0  # RPM 제어용 전역 타임스탬프
_gemini_cache: OrderedDict[str, object] = OrderedDict()  # LRU: 접근 시 move_to_end, 초과 시 popitem(last=False)
_gemini_cache_lock = threading.Lock()
_GEMINI_CACHE_MAX = 20

def _request_gemini(api_key: str, system_prompt: str, user_content: str, model_override: str | None = None) -> str:
    """Google Gemini API로 기획안을 생성합니다 (google-genai SDK). 시스템 프롬프트 캐싱 지원."""
    global _last_gemini_request_time
    import time as _time
    # RPM 제어: 최소 15초 간격
    elapsed = _time.time() - _last_gemini_request_time
    if elapsed < 15:
        _time.sleep(15 - elapsed)
    _last_gemini_request_time = _time.time()

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
                  reference_url: str | None = None,
                  format_type: str | None = None,
                  *, _skip_verify: bool = False, _skip_visual_director: bool = False,
                  _skip_polish: bool = False) -> tuple[list[dict[str, Any]], str, str, list[str]]:
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

    # System Prompt — 외부 파일에서 로드 (modules/gpt/prompts/)
    from modules.gpt.prompts import load_system_prompt, inject_channel_config, inject_format_prompt
    system_prompt = load_system_prompt(lang, channel)
    system_prompt = inject_channel_config(system_prompt, channel)
    if format_type:
        system_prompt = inject_format_prompt(system_prompt, format_type, lang)
        print(f"-> [포맷 주입] {format_type} ({lang})")

    # ── 이하 원본 인라인 프롬프트 (외부 파일로 이동됨) ──
    # 파일 위치: modules/gpt/prompts/system_{ko,en,es_us,es_latam}.txt
    # 채널 설정 주입: modules/gpt/prompts/__init__.py:inject_channel_config()

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

    # 채널×포맷별 min/max_cuts — 확장/트림 전에 먼저 계산
    from modules.utils.channel_config import get_channel_preset as _get_cuts_preset
    _cuts_preset = _get_cuts_preset(channel) if channel else None
    _format_cuts = (_cuts_preset or {}).get("format_cuts", {}).get(format_type or "", {}) if format_type else {}
    _cfg_max = _format_cuts.get("max") or (_cuts_preset or {}).get("max_cuts", 10)
    _cfg_min = _format_cuts.get("min") or (_cuts_preset or {}).get("min_cuts", 8)
    if _format_cuts:
        print(f"-> [포맷 컷 수] {format_type} × {channel}: {_cfg_min}~{_cfg_max}컷 적용")

    # 컷 수 검증 — 초과 시 트림, 부족 시 기존 컷 기반 확장 요청 (전체 재생성 방지)
    if len(cuts) > _cfg_max:
        print(f"-> [검증] 컷 수 {len(cuts)}개 → {_cfg_max}개로 트림")
        cuts = cuts[:_cfg_max]
    elif len(cuts) < _cfg_min:
        _fmt_label = f"[{format_type}] " if format_type else ""
        print(f"-> [검증 실패] {_fmt_label}컷 수가 {len(cuts)}개입니다. 기존 컷 기반 확장 요청합니다 (목표: {_cfg_min}~{_cfg_max}컷).")
        if llm_provider == "gemini":
            retry_key = get_google_key(None, service="gemini", exclude=exhausted_keys) or current_key
        else:
            retry_key = current_key
        # 포맷 시스템 프롬프트 재주입 (확장 요청에도 포맷 구조 규칙 적용)
        retry_system = inject_format_prompt(system_prompt, format_type, lang) if format_type else system_prompt
        # 기존 컷 데이터를 포함하여 확장만 요청 (전체 재생성 대신)
        existing_cuts_json = json.dumps(
            [{"script": c["script"], "description": c.get("text", ""), "image_prompt": c.get("prompt", "")} for c in cuts],
            ensure_ascii=False
        )
        if lang == "en":
            retry_expansion = (
                f"\n\nOnly {len(cuts)} cuts were generated. Expand to {_cfg_min}-{_cfg_max} total cuts. "
                f"You MUST keep ALL existing cuts verbatim and add NEW cuts between them to reinforce buildup/climax. "
                f"Return the complete expanded array.\nExisting cuts: {existing_cuts_json}"
            )
        elif lang == "es":
            retry_expansion = (
                f"\n\nSolo se generaron {len(cuts)} cortes. Expande a {_cfg_min}-{_cfg_max} cortes en total. "
                f"DEBES mantener TODOS los cortes existentes tal cual y agregar cortes NUEVOS entre ellos para reforzar el clímax. "
                f"Devuelve el array completo expandido.\nCortes existentes: {existing_cuts_json}"
            )
        else:
            retry_expansion = (
                f"\n\n기존에 {len(cuts)}컷만 생성되었습니다. 총 {_cfg_min}~{_cfg_max}컷으로 확장하세요. "
                f"기존 컷은 반드시 그대로 유지하고, 사이에 새 컷을 추가하여 빌드업/클라이맥스를 보강하세요. "
                f"확장된 전체 배열을 반환하세요.\n기존 컷: {existing_cuts_json}"
            )
        if lang == "en":
            retry_user = f"Topic: '{_safe_title}'." + retry_expansion
        elif lang == "es":
            retry_user = f"Tema: '{_safe_title}'." + retry_expansion
        else:
            retry_user = f"주제: '{_safe_title}'." + retry_expansion
        _original_cuts = cuts[:]
        try:
            expanded_cuts, title, tags, _ = _request_cuts(llm_provider, retry_key, retry_system, retry_user, model_override=llm_model)
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

    if len(cuts) < _cfg_min:
        raise ValueError(f"[HARD FAIL] 컷 수 {len(cuts)}개 — 채널 최소 {_cfg_min}컷 미달. 스크립트 재생성 필요.")

    # title이 비어있으면 제목을 폴백으로 사용 (자막 포함 방지)
    if not title:
        title = _topic_title

    # tags 기본값 보장
    if not tags or not isinstance(tags, list):
        tags = ["#Shorts"]

    # ── 3단계 검증 파이프라인 (최대 1회 재검증, 무한 루프 방지) ──
    # v2 오케스트라: _skip_verify=True면 QualityAgent가 별도 실행
    # 검증용 키: Gemini는 fresh 키 사용 (생성 후 429 위험 회피)
    def _verify_key():
        if llm_provider == "gemini":
            fresh = get_google_key(None, service="gemini", exclude=exhausted_keys)
            return fresh or current_key
        return current_key

    if not _skip_verify:
        # 순서: ① 하이네스 구조 → ② 주제 일치 → (구조가 스크립트를 바꿨으면 주제 재검증 1회)→ ③ 팩트
        _scripts_before = [c["script"] for c in cuts]

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
        # format_type을 각 컷에 첨부 (포맷별 HARD FAIL 검증용)
        if format_type:
            for _c in cuts:
                _c["format_type"] = format_type.upper()
        hard_fails = _validate_hard_fail(cuts, channel)

        # ⑤ 내러티브 아크 검증 — HOOK/LOOP/CLIMAX/PIVOT/RELEASE 구조 체크
        arc_issues = _validate_narrative_arc(cuts, lang)
        if arc_issues:
            print(f"⚠️ [아크 검증] {len(arc_issues)}개 구조 문제:")
            for issue in arc_issues:
                print(f"  - {issue}")
            # 아크 문제 → 구조 검증으로 1회 자동 수정
            has_hook_fail = any("ARC_HOOK" in i for i in arc_issues)
            has_loop_fail = any("ARC_LOOP" in i for i in arc_issues)
            has_climax_pivot = any("ARC_CLIMAX" in i or "ARC_PIVOT" in i for i in arc_issues)
            if has_hook_fail or has_loop_fail or has_climax_pivot:
                print("-> [아크 수정] 하이네스 구조 검증으로 자동 수정 시도...")
                cuts = _verify_highness_structure(cuts, _topic_title, llm_provider, _verify_key(), lang, llm_model, channel)
                arc_issues_retry = _validate_narrative_arc(cuts, lang)
                if arc_issues_retry:
                    print(f"  [아크] 수정 후 {len(arc_issues_retry)}개 남음 — 결과 유지")
                else:
                    print("OK [아크] 자동 수정 성공")
            if any("ARC_RELEASE" in i for i in arc_issues):
                print("  [아크 경고] 이완 컷 없음 — 수동 확인 권장 (자동 수정 생략)")
        else:
            print("OK [아크 검증] HOOK/LOOP/CLIMAX/PIVOT/RELEASE 통과")

        region_warns = _validate_region_style(cuts, channel)
        if hard_fails:
            print(f"⚠️ [HARD FAIL] {len(hard_fails)}개 품질 문제 감지:")
            for fail in hard_fails:
                print(f"  - {fail}")
            # HARD FAIL 유형별 수정 라우팅
            has_visual_fail = any("VISUAL" in f for f in hard_fails)
            has_structure_fail = any(k in "".join(hard_fails) for k in ["HOOK", "TENSION", "LOOP", "TONE"])
            has_academic_fail = any("ACADEMIC" in f for f in hard_fails)
            if has_academic_fail:
                print("-> [HARD FAIL 수정] 학술체 리라이트 시도...")
                cuts = _rewrite_academic_tone(cuts, lang, llm_provider, _verify_key(), llm_model)
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
    else:
        print(f"[v2] 검증 스킵 (QualityAgent가 별도 실행)")

    # ── 비주얼 디렉터: image_prompt 전문 리라이트 (컷1 특별 강화) ──
    if not _skip_visual_director:
        try:
            _vd_key = _verify_key()
            cuts = _enhance_image_prompts(cuts, _topic_title, lang, _vd_key, channel)
            # 비주얼 디렉터 후 주제 일치 재검증 (공룡 같은 무관 피사체 방지)
            cuts = _verify_subject_match(cuts, _topic_title, llm_provider, _verify_key(), lang, llm_model)
        except Exception as _vd_err:
            print(f"[비주얼 디렉터] 스킵 (원본 유지): {_vd_err}")
    else:
        print(f"[v2] 비주얼 디렉터 스킵 (VisualDirectorAgent가 별도 실행)")

    print(f"OK [기획 전문가] 기획안 완성! ({len(cuts)}컷, {provider_label}) 제목: {title} | 태그: {', '.join(tags)}")

    # ── 채널 금지 표현 필터링 + 문장 자연화 ──
    if not _skip_polish:
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
    else:
        print(f"[v2] 폴리시 스킵 (PolishAgent가 별도 실행)")

    # v2 오케스트라 모드: fact_context도 반환 (QualityAgent에서 사용)
    if _skip_verify or _skip_polish or _skip_visual_director:
        return cuts, topic_folder, title, tags, video_description, fact_context

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
        for tag in ["SHOCK", "WONDER", "TENSION", "REVEAL", "URGENCY", "DISBELIEF", "IDENTITY"]:
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

            # script 또는 description 수정 (글자수 보호: 수정 후 더 짧아지면 거부)
            if field == "script" and new_val != cuts[idx].get("script"):
                old = cuts[idx]["script"]
                # 한국어: 수정 후 20자 미만이면 거부, 영어/스페인어: 8단어 미만이면 거부
                if len(new_val) < len(old) * 0.6:
                    print(f"  [구조 수정 거부] 컷{idx+1} 글자수 40%+ 감소 ({len(old)}→{len(new_val)}) — 원본 유지")
                    continue
                if len(new_val) < 15:
                    print(f"  [구조 수정 거부] 컷{idx+1} 수정 후 15자 미만 ({len(new_val)}자) — 원본 유지")
                    continue
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
                new_script = item["verified"]
                # 글자수 보호: 수정 후 40%+ 줄어들면 거부
                if len(new_script) < len(old_script) * 0.6:
                    print(f"  [팩트 수정 거부] 컷{idx+1} 글자수 40%+ 감소 ({len(old_script)}→{len(new_script)}) — 원본 유지")
                    continue
                if len(new_script) < 15:
                    print(f"  [팩트 수정 거부] 컷{idx+1} 15자 미만 ({len(new_script)}자) — 원본 유지")
                    continue
                cuts[idx]["script"] = new_script
                changed_count += 1
                print(f"  [팩트 수정] 컷{idx+1}: '{old_script[:30]}...' → '{new_script[:30]}...' ({item.get('reason', '')})")

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

    # 1-b) Hook 길이 강제 — 채널별 Cut1 글자/단어 수 제한
    if channel:
        from modules.utils.channel_config import get_channel_preset as _get_hook_preset
        _hook_preset = _get_hook_preset(channel)
        _hook_lang = (_hook_preset or {}).get("language", "en")
        if _hook_lang == "ko":
            # 한국어: 15자 초과 시 reject
            if len(first_script.replace(" ", "")) > 15:
                failures.append(f"HOOK_TOO_LONG: KO 훅 {len(first_script.replace(' ', ''))}자 (최대 15자) — '{first_script[:30]}'")
        elif _hook_lang == "en":
            # 영어: 10단어 초과 시 reject
            word_count = len(first_script.split())
            if word_count > 10:
                failures.append(f"HOOK_TOO_LONG: EN 훅 {word_count}단어 (최대 10) — '{first_script[:40]}'")
        elif _hook_lang == "es":
            # 스페인어: 12단어 초과 시 reject
            word_count = len(first_script.split())
            if word_count > 12:
                failures.append(f"HOOK_TOO_LONG: ES 훅 {word_count}단어 (최대 12) — '{first_script[:40]}'")

    # 2) 긴장 상승 검증 — 감정 태그 다양성
    emotions = []
    for c in cuts:
        desc = c.get("text", "") or c.get("description", "")
        for tag in ["SHOCK", "WONDER", "TENSION", "REVEAL", "URGENCY", "DISBELIEF", "IDENTITY"]:
            if tag in desc.upper():
                emotions.append(tag)
                break
    if len(set(emotions)) < 3:
        failures.append(f"TENSION_FLAT: 감정 태그 {len(set(emotions))}종류 (최소 3 필요)")
    # 2연속 동일 감정 태그 체크
    for i in range(1, len(emotions)):
        if emotions[i] == emotions[i-1]:
            failures.append(f"EMOTION_REPEAT: 컷 {i}~{i+1} 동일 태그 [{emotions[i]}] 연속")

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

    # 5) 학술체 감지 — "연구에 따르면" 등 학술적 도입부
    academic_patterns_ko = ["연구에 따르면", "과학자들이 발견", "에 의하면", "것으로 밝혀", "것으로 알려져", "분석에 따르면", "논문에 따르면"]
    academic_patterns_en = ["according to", "studies show", "researchers found", "scientists discovered", "research suggests", "a study published"]
    academic_patterns_es = ["según estudios", "los científicos descubrieron", "investigaciones demuestran", "un estudio publicado"]
    all_scripts_combined = " ".join(c.get("script", "") for c in cuts).lower()
    for pat in academic_patterns_ko + academic_patterns_en + academic_patterns_es:
        if pat.lower() in all_scripts_combined:
            # 어떤 컷에서 발견됐는지 찾기
            for ci, c in enumerate(cuts):
                if pat.lower() in c.get("script", "").lower():
                    failures.append(f"ACADEMIC_TONE: Cut {ci+1}에 학술체 '{pat}' — '{c['script'][:50]}'")

    # 6) 포맷별 구조 검증 (format_type이 cuts에 첨부된 경우)
    fmt_type = (cuts[0].get("format_type") or "").upper() if cuts else ""

    if fmt_type == "WHO_WINS":
        # 컷1 반드시 [SHOCK]
        first_desc = cuts[0].get("description", cuts[0].get("text", ""))
        if "SHOCK" not in first_desc.upper():
            failures.append("FORMAT_WHO_WINS: 컷1 [SHOCK] 태그 없음 — 대결 선언 컷 필수")
        # REVEAL이 후반부(컷7 이후)에 있어야 함 (너무 일찍 승자 공개 방지)
        for ci, c in enumerate(cuts[:min(6, len(cuts))]):
            desc = c.get("description", c.get("text", ""))
            if "REVEAL" in desc.upper():
                failures.append(f"FORMAT_WHO_WINS: 컷{ci+1} 조기 [REVEAL] — 승자는 컷7 이후 공개 필요")
                break

    elif fmt_type == "EMOTIONAL_SCI":
        # 컷1에 [SHOCK] 있으면 포맷 위반
        first_desc = cuts[0].get("description", cuts[0].get("text", ""))
        if "SHOCK" in first_desc.upper():
            failures.append("FORMAT_EMOTIONAL_SCI: 컷1 [SHOCK] 금지 — 감성과학은 [WONDER]로 시작 필수")
        # [WONDER] 또는 [IDENTITY] 최소 2컷 이상
        warm_count = sum(
            1 for c in cuts
            if any(t in (c.get("description", "") or c.get("text", "")).upper()
                   for t in ("WONDER", "IDENTITY"))
        )
        if warm_count < 2:
            failures.append(f"FORMAT_EMOTIONAL_SCI: WONDER/IDENTITY 태그 {warm_count}컷 (최소 2 필요)")

    elif fmt_type == "IF":
        # 컷1 반드시 [SHOCK]
        first_desc = cuts[0].get("description", cuts[0].get("text", ""))
        if "SHOCK" not in first_desc.upper():
            failures.append("FORMAT_IF: 컷1 [SHOCK] 태그 없음 — 가정 선언 컷 필수")

    # 7) 톤-채널 일치 검증
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


def _validate_narrative_arc(cuts: list[dict], lang: str = "ko") -> list[str]:
    """narrative_blueprint 아크 코드 검증 — 감정 태그 기반, LLM 호출 없음.

    검증 항목:
    1. HOOK: 첫 컷 강한 감정 (SHOCK/URGENCY/DISBELIEF)
    2. LOOP: 마지막 컷 열린 마무리 감정 (SHOCK/URGENCY 끝 금지)
    3. CLIMAX: 후반부(컷5~끝-1)에 SHOCK/REVEAL/URGENCY 존재
    4. PIVOT: 중반부(컷3~5)에 REVEAL/SHOCK 존재 (두 번째 훅)
    5. RELEASE: WONDER/CALM/IDENTITY 최소 1개
    """
    _EMOTION_RE = re.compile(
        r'\[(SHOCK|WONDER|TENSION|REVEAL|URGENCY|DISBELIEF|IDENTITY|CALM)\]', re.IGNORECASE
    )
    emotions: list[str | None] = []
    for cut in cuts:
        m = _EMOTION_RE.search(cut.get("description", "") or cut.get("text", ""))
        emotions.append(m.group(1).upper() if m else None)

    if not emotions or len(emotions) < 4:
        return []  # 컷 수 부족은 다른 검증에서 처리

    issues: list[str] = []

    # 1. HOOK: 첫 컷은 강한 감정 필수
    high_emotions = {"SHOCK", "URGENCY", "DISBELIEF"}
    if emotions[0] not in high_emotions:
        issues.append(
            f"ARC_HOOK: 첫 컷 감정 [{emotions[0]}] 약함 — SHOCK/URGENCY/DISBELIEF 필요"
        )

    # 2. LOOP: 마지막 컷은 열린 마무리 (SHOCK/URGENCY로 끝나면 루프 안 됨)
    if emotions[-1] in ("SHOCK", "URGENCY"):
        issues.append(
            f"ARC_LOOP: 마지막 컷 [{emotions[-1]}] — 루프 엔딩에 부적합. CALM/WONDER/IDENTITY 권장"
        )

    # 3. CLIMAX: 후반부(컷5~끝-1)에 임팩트 감정 존재
    climax_emotions = {"SHOCK", "REVEAL", "URGENCY", "DISBELIEF"}
    climax_range = emotions[4:-1] if len(emotions) > 5 else emotions[3:-1]
    if climax_range and not any(e in climax_emotions for e in climax_range if e):
        issues.append(
            "ARC_CLIMAX: 후반부 클라이맥스 없음 — 컷5~끝-1에 SHOCK/REVEAL/URGENCY 필요"
        )

    # 4. PIVOT: 중반부(컷3~5)에 두 번째 훅 (REVEAL or SHOCK)
    pivot_range = emotions[2:5] if len(emotions) > 4 else emotions[2:]
    pivot_emotions = {"REVEAL", "SHOCK", "DISBELIEF", "URGENCY"}
    if pivot_range and not any(e in pivot_emotions for e in pivot_range if e):
        issues.append(
            "ARC_PIVOT: 중반부(컷3~5) 두 번째 훅 없음 — REVEAL/SHOCK/URGENCY 필요"
        )

    # 5. RELEASE: 이완 컷 (WONDER/CALM/IDENTITY) 최소 1개
    release_emotions = {"WONDER", "CALM", "IDENTITY"}
    if not any(e in release_emotions for e in emotions if e):
        issues.append(
            "ARC_RELEASE: 이완 컷 없음 — WONDER/CALM/IDENTITY 최소 1개 필요 (파도형 리듬)"
        )

    return issues


def _enhance_image_prompts(cuts: list[dict], topic: str, lang: str, api_key: str, channel: str | None = None) -> list[dict]:
    """비주얼 디렉터 — image_prompt 전문 리라이트. 컷1은 스크롤 멈추기 특별 강화."""
    if not cuts or not api_key:
        return cuts

    print("-> [비주얼 디렉터] image_prompt 최적화 중...")

    # 채널별 비주얼 스타일 (channel_config.py에서 가져옴 — 데이터 일원화)
    from modules.utils.channel_config import get_channel_preset
    _preset = get_channel_preset(channel) if channel else None
    channel_style = (_preset or {}).get("visual_style", "cinematic realism, dramatic lighting")

    scripts_and_prompts = []
    for i, cut in enumerate(cuts):
        scripts_and_prompts.append({
            "cut": i + 1,
            "script": cut.get("script", ""),
            "current_prompt": cut.get("prompt", ""),
        })

    prompt = f"""You are a world-class visual director for viral YouTube Shorts. Your ONLY job is to rewrite image_prompts to maximize scroll-stopping power.

Topic: {topic}
Channel style: {channel_style}
Language: {lang}

RULES:
- CRITICAL: Do NOT introduce ANY subject not present in the script. The main subject in each script line MUST be the main subject in the image_prompt. Adding unrelated subjects (dinosaurs, animals, people) that are not in the script = FAIL.
- Cut 1 is the MOST IMPORTANT. It MUST stop the scroll. Include at least 2: extreme scale contrast, intense color contrast, surreal/impossible scene, eye-locking composition.
- Every image_prompt must START with the main subject from the script.
- Describe SCENES, not keywords. Full sentences produce better images.
- Each cut must use a DIFFERENT camera technique (close-up, wide shot, aerial, macro, etc.)
- 9:16 vertical composition: place subject in upper or lower 1/3, leave top 15% and bottom 20% clear for subtitles.
- Negative constraints: NO text, NO watermark, NO logo, NO diagrams, NO infographic, NO cartoon, NO anime, NO illustration.
- 40-60 words per prompt (Cut 1 may use up to 65 words).
- Output ONLY a JSON array of objects: [{{"cut": 1, "image_prompt": "..."}}, ...]

Current cuts:
{json.dumps(scripts_and_prompts, ensure_ascii=False)}

IMPORTANT — Color Continuity:
- All cuts in the same episode MUST share a consistent dominant color palette.
- Space topics: consistent deep blue-black color space throughout
- Dinosaur/prehistoric: consistent warm amber-green jungle palette
- Ocean/deep sea: consistent dark teal-blue underwater palette
- Earth/geology: consistent warm earth tones throughout
- Pick ONE dominant hue and maintain it across all cuts.

Rewrite ALL image_prompts. Make Cut 1 DRAMATICALLY more visually striking than the rest."""

    try:
        raw = _request_gemini_freeform(api_key, prompt, "gemini-2.5-flash")
        result = _extract_json(raw)

        if not isinstance(result, list):
            print(f"  [비주얼 디렉터] 응답 파싱 실패 — 원본 유지")
            return cuts

        enhanced_count = 0
        for item in result:
            if not isinstance(item, dict):
                continue
            idx = item.get("cut", 0) - 1
            new_prompt = item.get("image_prompt", "")
            if not new_prompt or not (0 <= idx < len(cuts)):
                continue

            # 길이 검증: 너무 짧거나 길면 스킵
            if len(new_prompt) < 20 or len(new_prompt) > 500:
                continue

            old_prompt = cuts[idx].get("prompt", "")
            cuts[idx]["prompt"] = new_prompt
            enhanced_count += 1

            if idx == 0:
                print(f"  [비주얼 디렉터] 컷1 image_prompt 강화 완료")

        if enhanced_count > 0:
            print(f"OK [비주얼 디렉터] {enhanced_count}개 컷 image_prompt 최적화 완료")
        else:
            print(f"  [비주얼 디렉터] 변경 없음 — 원본 유지")

    except Exception as e:
        print(f"  [비주얼 디렉터] 에러 — 원본 유지: {e}")

    return cuts


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
    """Gemini에 자유형 프롬프트 전송 (스키마 없음). RPM 제어 포함."""
    global _last_gemini_request_time
    import time as _time
    # RPM 제어: 최소 15초 간격 (분당 4회 이하)
    elapsed = _time.time() - _last_gemini_request_time
    if elapsed < 15:
        _time.sleep(15 - elapsed)
    _last_gemini_request_time = _time.time()

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


# ── 학술체 리라이트 ─────────────────────────────────────────────────

def _rewrite_academic_tone(cuts: list[dict], lang: str, llm_provider: str, api_key: str, model: str | None = None) -> list[dict]:
    """학술체 표현을 펀치력 있는 구어체로 리라이트."""
    academic_patterns = {
        "ko": ["연구에 따르면", "과학자들이 발견", "에 의하면", "것으로 밝혀", "것으로 알려져", "분석에 따르면", "논문에 따르면"],
        "en": ["according to", "studies show", "researchers found", "scientists discovered", "research suggests", "a study published"],
        "es": ["según estudios", "los científicos descubrieron", "investigaciones demuestran", "un estudio publicado"],
    }
    patterns = academic_patterns.get(lang, academic_patterns["en"])

    # 학술체가 포함된 컷만 추출
    targets = []
    for i, cut in enumerate(cuts):
        script = cut.get("script", "")
        if any(p.lower() in script.lower() for p in patterns):
            targets.append({"cut": i + 1, "script": script})

    if not targets:
        return cuts

    rewrite_rules = {
        "ko": "학술적 도입부를 제거하고 팩트를 바로 던지는 반말 구어체로 바꿔라. 의미는 유지. 예: '연구에 따르면 이 물질은 독성이 있어' → '이 물질, 금보다 독해'",
        "en": "Remove academic introductions and state the fact directly. Keep meaning. Example: 'According to NASA, this planet has diamond rain' → 'This planet rains diamonds.'",
        "es": "Elimina introducciones académicas y di el dato directamente. Mantén el significado. Ejemplo: 'Según estudios, este animal...' → 'Este animal...'",
    }

    prompt = f"""Rewrite ONLY the scripts below to remove academic/research-framing language.
Rule: {rewrite_rules.get(lang, rewrite_rules['en'])}

Scripts to fix:
{json.dumps(targets, ensure_ascii=False)}

Output JSON array: [{{"cut": 1, "script": "rewritten"}}]
ONLY output scripts that were changed. Keep same length range."""

    try:
        import json as _json
        raw = _request_gemini_freeform(api_key, prompt, model)
        rewrites = _json.loads(raw)
        if isinstance(rewrites, list):
            for rw in rewrites:
                idx = rw.get("cut", 0) - 1
                new_script = rw.get("script", "")
                if 0 <= idx < len(cuts) and new_script:
                    old = cuts[idx]["script"]
                    cuts[idx]["script"] = new_script
                    print(f"  [학술체 리라이트] Cut {idx+1}: '{old[:30]}' → '{new_script[:30]}'")
    except Exception as e:
        print(f"  [학술체 리라이트] 실패 (원본 유지): {e}")

    return cuts


# ── 문장 자연화 리라이트 (Script Polisher) ─────────────────────────


def _get_sentence_polish_prompt(lang: str, channel: str | None = None) -> str:
    """채널별 문장 다듬기 프롬프트를 반환합니다."""
    if channel == "askanything":
        return """너는 한국어 쇼츠 대본 문장 다듬기 전문가다. 친구한테 신기한 얘기 해주는 느낌으로.

핵심 원칙:
- 소리 내서 읽었을 때 자연스러워야 한다. 어색하면 실패.
- 번역투/설명체/교과서체를 전부 없앤다.
- 한국어 어순: 핵심 단어를 앞에 놓아라.

★ 자주 나오는 나쁜 패턴 → 고치는 법:
❌ "이것은 매우 독특한 특성을 가지고 있어" → ✅ "이거 진짜 특이해"
❌ "그것이 발견된 이유는 ~때문이야" → ✅ "발견된 이유? ~때문이야"
❌ "이 생물은 어둠 속에서 빛을 만들어내" → ✅ "이 생물, 어둠 속에서 스스로 빛나"
❌ "그 결과로 인해 ~하게 되었어" → ✅ "그래서 ~됐어"
❌ "이것은 ~라고 할 수 있어" → ✅ "~인 거야"
❌ "~하는 것으로 알려져 있어" → ✅ "~하거든"
❌ "이 현상은 ~에 의해 발생해" → ✅ "~가 이걸 만들어"
❌ "약 50%에 달하는 비율이야" → ✅ "절반이야"
❌ "~할 수 있는 능력을 가지고 있어" → ✅ "~할 수 있어"

★ 어미 다양성 (같은 어미 2번 연속 금지):
"~야" "~거든" "~잖아" "~거야" "~인데" "~라는 거지" "~알아?"
이 중에서 골고루 섞어 써라.

★ 리듬감:
짧은 문장(15자) → 긴 문장(30자) → 짧은 문장 교대.
3문장 연속 같은 길이 금지.

반드시 지킬 것:
- 컷 수 유지, 각 컷 한 문장
- 원래 정보 추가/삭제 금지
- "미쳤다", "레전드", "ㄹㅇ", "ㅋㅋ" 금지
- 훅은 더 세게 만들 수는 있어도 약하게 만들면 안 됨

출력: JSON만
{"rewritten_scripts": ["컷1", "컷2"], "notes": ["수정 메모"]}"""

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
