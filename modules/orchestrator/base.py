"""BaseAgent, AgentContext, ModelRouter, TokenUsage.

모든 에이전트의 공통 인터페이스와 공유 상태를 정의.
"""

from __future__ import annotations

import os
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator


# ────────────────────────────────────────────
# TokenUsage: 단일 LLM 호출 토큰 기록
# ────────────────────────────────────────────
@dataclass
class TokenUsage:
    agent: str
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    timestamp: float = field(default_factory=time.time)


# ────────────────────────────────────────────
# AgentContext: 에이전트 간 공유 상태
# ────────────────────────────────────────────
@dataclass
class AgentContext:
    """오케스트라 파이프라인의 공유 상태.

    각 에이전트가 읽고/쓰는 필드가 명확히 구분됨.
    오케스트라가 생성하고, 에이전트는 자기 담당 필드만 기록.
    """

    # ── 요청 식별 ──
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    # ── 입력 (오케스트라가 설정) ──
    topic: str = ""
    language: str = "ko"
    channel: str | None = None
    reference_url: str | None = None
    format_type: str | None = None  # WHO_WINS / IF / EMOTIONAL_SCI / FACT

    # ── LLM 설정 ──
    llm_provider: str = "gemini"
    llm_model: str | None = None
    llm_key: str | None = None

    # ── 이미지/비디오/TTS 설정 ──
    image_engine: str = "imagen"
    image_model: str | None = None
    video_engine: str = "veo3"
    video_model: str = "hero-only"
    voice_id: str | None = None
    voice_settings: dict | None = None
    tts_speed: float = 0.9
    camera_style: str = "auto"
    bgm_theme: str = "random"
    platforms: list[str] = field(default_factory=lambda: ["youtube"])
    caption_size: int = 48
    caption_y: int = 28

    # ── 파이프라인 상태 (에이전트가 기록) ──
    cuts: list[dict[str, Any]] = field(default_factory=list)
    title: str = ""
    tags: list[str] = field(default_factory=list)
    description: str = ""
    topic_folder: str = ""
    fact_context: str = ""

    # ── 에셋 경로 (ImageAgent, TTSAgent, RenderAgent 기록) ──
    visual_paths: list[str | None] = field(default_factory=list)
    audio_paths: list[str | None] = field(default_factory=list)
    word_timestamps: list[list | None] = field(default_factory=list)
    scripts: list[str] = field(default_factory=list)
    cut1_ab_variants: list[str] = field(default_factory=list)
    video_paths: dict[str, str] = field(default_factory=dict)
    thumbnail_path: str | None = None

    # ── 업로드 결과 ──
    upload_results: list[dict] = field(default_factory=list)

    # ── 퍼블리시 설정 ──
    publish_mode: str = "local"
    scheduled_time: str | None = None
    workflow_mode: str = "fast"
    max_cuts: int | None = None

    # ── API 키 오버라이드 ──
    api_key_override: str | None = None
    elevenlabs_key: str | None = None
    gemini_keys_override: str | None = None

    # ── 토큰 추적 ──
    token_log: list[TokenUsage] = field(default_factory=list)

    # ── 비용 카운팅 (ImageAgent/VideoAgent/TTSAgent 기록) ──
    image_count: int = 0
    video_count: int = 0
    tts_chars: int = 0

    # ── 취소 ──
    _cancelled: bool = False

    def is_cancelled(self) -> bool:
        return self._cancelled

    def cancel(self):
        self._cancelled = True

    def record_tokens(self, usage: TokenUsage):
        self.token_log.append(usage)

    def total_cost(self) -> float:
        return sum(u.cost_usd for u in self.token_log)

    def cost_by_agent(self) -> dict[str, float]:
        result: dict[str, float] = {}
        for u in self.token_log:
            result[u.agent] = result.get(u.agent, 0.0) + u.cost_usd
        return result


# ────────────────────────────────────────────
# ModelRouter: Gemini 중심 모델 선택
# ────────────────────────────────────────────
class ModelRouter:
    """에이전트별 최적 모델 선택. Gemini 우선, 429 시 폴백."""

    def __init__(self, overrides: dict[str, str] | None = None):
        """overrides: {"ScriptAgent": "gemini-2.5-flash"} 식으로 강제 지정."""
        self._overrides = overrides or {}

    def select(self, agent_name: str, ctx: AgentContext) -> 'ModelSpec':
        from modules.orchestrator.config import MODELS, AGENT_MODEL_DEFAULTS

        # 1. 명시적 오버라이드
        override_id = self._overrides.get(agent_name)
        if not override_id and ctx.llm_model and agent_name == "ScriptAgent":
            override_id = ctx.llm_model

        if override_id and override_id in MODELS:
            return MODELS[override_id]

        # 2. 에이전트 기본 → 폴백 체인
        defaults = AGENT_MODEL_DEFAULTS.get(agent_name, {})
        preferred = defaults.get("preferred", [])
        fallback = defaults.get("fallback", [])

        for model_id in preferred + fallback:
            spec = MODELS.get(model_id)
            if spec and self._is_provider_available(spec.provider, ctx):
                return spec

        # 절대 폴백
        return MODELS["gemini-2.5-flash"]

    def on_429(self, agent_name: str, failed_model_id: str, ctx: AgentContext) -> 'ModelSpec | None':
        """429 에러 시 다음 폴백 모델 반환. None이면 더 이상 폴백 없음."""
        from modules.orchestrator.config import MODELS, AGENT_MODEL_DEFAULTS

        defaults = AGENT_MODEL_DEFAULTS.get(agent_name, {})
        chain = defaults.get("preferred", []) + defaults.get("fallback", [])

        # 실패한 모델 이후의 체인에서 사용 가능한 것 선택
        found_failed = False
        for model_id in chain:
            if model_id == failed_model_id:
                found_failed = True
                continue
            if found_failed:
                spec = MODELS.get(model_id)
                if spec and self._is_provider_available(spec.provider, ctx):
                    return spec
        return None

    @staticmethod
    def _is_provider_available(provider: str, ctx: AgentContext) -> bool:
        if provider == "gemini":
            from modules.utils.keys import count_available_keys
            return count_available_keys(extra_keys=ctx.gemini_keys_override) > 0
        elif provider == "openai":
            key = ctx.api_key_override or os.getenv("OPENAI_API_KEY", "")
            return bool(key) and not key.startswith("sk-proj-YOUR")
        elif provider == "claude":
            return bool(os.getenv("ANTHROPIC_API_KEY", ""))
        return False


# ────────────────────────────────────────────
# BaseAgent: 모든 에이전트의 공통 인터페이스
# ────────────────────────────────────────────
class BaseAgent(ABC):
    """에이전트 기본 클래스.

    규칙:
    - 에이전트는 상태를 가지지 않음 (상태는 AgentContext에만 존재)
    - 기존 모듈 함수를 호출하되, 재작성하지 않음
    - execute()는 SSE 문자열을 yield
    """

    name: str = "BaseAgent"

    def __init__(self, router: ModelRouter, tracker: 'TokenTracker'):
        self._router = router
        self._tracker = tracker

    @abstractmethod
    async def execute(self, ctx: AgentContext) -> AsyncGenerator[str, None]:
        """에이전트 실행. SSE 문자열 yield.

        규약:
          "PROG|{pct}"   — 진행률
          "WARN|message"  — 경고
          "ERROR|message" — 에러
          일반 텍스트      — 정보 메시지
        """
        yield ""  # pragma: no cover

    def _select_model(self, ctx: AgentContext):
        return self._router.select(self.name, ctx)

    def _get_llm_key(self, ctx: AgentContext, service: str = "gemini") -> str:
        """프로바이더에 맞는 API 키 반환. Vertex AI 모드면 None (SA 인증)."""
        spec = self._select_model(ctx)
        if spec.provider == "gemini":
            # Vertex AI: 서비스 계정 인증 → API 키 불필요
            if os.getenv("GEMINI_BACKEND") == "vertex_ai":
                return ""
            from modules.utils.keys import get_google_key
            return get_google_key(ctx.llm_key, service=service,
                                  extra_keys=ctx.gemini_keys_override) or ""
        elif spec.provider == "openai":
            return ctx.api_key_override or os.getenv("OPENAI_API_KEY", "")
        elif spec.provider == "claude":
            return ctx.llm_key or os.getenv("ANTHROPIC_API_KEY", "")
        return ""

    def _call_llm(self, ctx: AgentContext, system_prompt: str,
                  user_content: str, freeform: bool = False) -> str:
        """통합 LLM 호출. 모델 라우터 → 기존 cutter.py 함수 호출 → 429 폴백 → 토큰 기록.

        기존 _request_gemini/_request_openai/_request_claude를 직접 호출하여
        Gemini 캐싱, RPM 쓰로틀링 등 기존 로직을 그대로 활용.
        """
        spec = self._select_model(ctx)
        key = self._get_llm_key(ctx)

        content = self._dispatch_llm_call(spec, key, system_prompt, user_content, freeform)

        # 토큰 추정 (문자 기반, Phase 2에서 SDK 메타데이터로 교체)
        input_chars = len(system_prompt) + len(user_content)
        output_chars = len(content) if content else 0
        self._tracker.record(
            self.name, spec.model_id,
            input_tokens=input_chars // 4,
            output_tokens=output_chars // 4,
        )

        return content or ""

    def _dispatch_llm_call(self, spec, key: str, system_prompt: str,
                           user_content: str, freeform: bool) -> str:
        """실제 LLM API 호출 디스패치."""
        from modules.gpt.cutter import (
            _request_gemini, _request_openai, _request_openai_freeform,
            _request_claude,
        )

        if spec.provider == "gemini":
            return _request_gemini(key, system_prompt, user_content, spec.model_id)
        elif spec.provider == "claude":
            return _request_claude(key, system_prompt, user_content, spec.model_id)
        elif freeform:
            return _request_openai_freeform(key, system_prompt, user_content, spec.model_id)
        else:
            return _request_openai(key, system_prompt, user_content, spec.model_id)
