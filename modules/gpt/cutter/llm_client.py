import os
import time
import hashlib
import threading
from collections import OrderedDict
from typing import Any

from .parser import _parse_cuts, _extract_json

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
    from modules.utils.gemini_client import create_gemini_client
    model_name = model_override or os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
    client = create_gemini_client(api_key=api_key)
    use_context_cache = (
        os.getenv("GEMINI_CONTEXT_CACHE", "1").lower() not in {"0", "false", "no", "off"}
        and os.getenv("GEMINI_BACKEND", "").lower().strip() != "vertex_ai"
    )

    def _generate_with_system_instruction() -> str:
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

    if not use_context_cache:
        return _generate_with_system_instruction()

    # Context Caching: 시스템 프롬프트를 캐시하여 토큰 비용 절감
    # 캐시 키에 프롬프트 해시 포함 (lang/channel 변경 시 잘못된 캐시 사용 방지)
    prompt_hash = hashlib.sha256(system_prompt.encode()).hexdigest()
    cache_identity = api_key or f"{os.getenv('GEMINI_BACKEND', 'ai_studio')}:{model_name}"
    key_hash = hashlib.sha256(cache_identity.encode()).hexdigest()[:16]
    cache_key = f"{key_hash}:{model_name}:{prompt_hash}"
    cached = None
    with _gemini_cache_lock:
        _cached_ref = _gemini_cache.get(cache_key)
        if _cached_ref:
            _gemini_cache.move_to_end(cache_key)  # LRU: 최근 접근으로 이동
            cached = _cached_ref  # 락 안에서 로컬 변수로 복사
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
        # 캐시 생성 후 generate 실패 → 캐시 정리
        with _gemini_cache_lock:
            _gemini_cache.pop(cache_key, None)
        # 캐시 미지원 모델이거나 에러 → 일반 요청
        return _generate_with_system_instruction()
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
