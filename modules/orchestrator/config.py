"""모델 카탈로그, 에이전트별 기본 모델, 토큰 예산.

핵심 원칙:
  - 기본 LLM은 Gemini (Pro=창작, Flash=검증/폴리시)
  - OpenAI/GPT는 프로젝트 정책상 폴백에서 제외
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    """LLM 모델 사양."""
    provider: str            # "gemini", "openai", "claude"
    model_id: str            # "gemini-2.5-pro" 등
    cost_tier: str           # "cheap", "medium", "expensive"
    input_price_per_1m: float   # USD / 1M input tokens
    output_price_per_1m: float  # USD / 1M output tokens


# ── 모델 카탈로그 (2026-04 기준) ──
MODELS: dict[str, ModelSpec] = {
    # Gemini (무료 API 키 기준)
    "gemini-2.5-pro": ModelSpec("gemini", "gemini-2.5-pro", "expensive", 1.25, 10.0),
    "gemini-2.5-flash": ModelSpec("gemini", "gemini-2.5-flash", "medium", 0.15, 0.60),
    "gemini-2.0-flash": ModelSpec("gemini", "gemini-2.0-flash", "cheap", 0.10, 0.40),
    # Claude (유료)
    "claude-sonnet-4-20250514": ModelSpec("claude", "claude-sonnet-4-20250514", "medium", 3.0, 15.0),
    "claude-haiku-4-5-20251001": ModelSpec("claude", "claude-haiku-4-5-20251001", "cheap", 0.80, 4.0),
    # OpenAI (유료, 정책상 기본 라우팅 제외)
    "gpt-4o": ModelSpec("openai", "gpt-4o", "medium", 2.50, 10.0),
    "gpt-4o-mini": ModelSpec("openai", "gpt-4o-mini", "cheap", 0.15, 0.60),
    "gpt-4.1": ModelSpec("openai", "gpt-4.1", "medium", 2.0, 8.0),
    "gpt-4.1-mini": ModelSpec("openai", "gpt-4.1-mini", "cheap", 0.40, 1.60),
}

# ── 에이전트별 기본 모델 + 폴백 체인 ──
# 기본은 무조건 Gemini. 폴백은 429/장애 시에만 진행.
AGENT_MODEL_DEFAULTS: dict[str, dict] = {
    "ScriptAgent": {
        "preferred": ["gemini-2.5-pro"],
        "fallback": ["gemini-2.5-flash", "gemini-2.0-flash"],
    },
    "QualityAgent": {
        "preferred": ["gemini-2.5-flash"],
        "fallback": ["gemini-2.0-flash"],
    },
    "VisualDirectorAgent": {
        "preferred": ["gemini-2.5-flash"],
        "fallback": ["gemini-2.0-flash"],
    },
    "PolishAgent": {
        "preferred": ["gemini-2.5-flash"],
        "fallback": ["gemini-2.0-flash"],
    },
}

# ── 토큰 예산 (에이전트별 + 요청 전체) ──
TOKEN_BUDGETS: dict[str, int] = {
    "ScriptAgent": 25_000,
    "QualityAgent": 15_000,
    "VisualDirectorAgent": 8_000,
    "PolishAgent": 5_000,
    "total_request": 60_000,
}
