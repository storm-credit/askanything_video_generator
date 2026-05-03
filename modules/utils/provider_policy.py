"""Provider policy helpers for globally disabled paid providers."""

from __future__ import annotations

import os


_TRUE_VALUES = {"1", "true", "yes", "on"}


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in _TRUE_VALUES


def is_openai_api_disabled() -> bool:
    """Return True when OpenAI calls must be blocked even if a key exists."""
    return (
        _truthy("OPENAI_API_DISABLED")
        or _truthy("DISABLE_OPENAI_API")
        or _truthy("NO_OPENAI_API")
        or _truthy("VERTEX_SA_ONLY")
    )


def openai_disabled_reason() -> str:
    if _truthy("VERTEX_SA_ONLY"):
        return "VERTEX_SA_ONLY=true"
    if _truthy("OPENAI_API_DISABLED"):
        return "OPENAI_API_DISABLED=true"
    if _truthy("DISABLE_OPENAI_API"):
        return "DISABLE_OPENAI_API=true"
    if _truthy("NO_OPENAI_API"):
        return "NO_OPENAI_API=true"
    return ""


def get_openai_api_key(override: str | None = None) -> str:
    """Return an OpenAI key only when project policy allows OpenAI calls."""
    if is_openai_api_disabled():
        return ""
    return (override or os.getenv("OPENAI_API_KEY") or "").strip()


def require_openai_api_enabled(feature: str = "OpenAI API") -> None:
    """Raise a user-facing error if the project policy blocks OpenAI calls."""
    if is_openai_api_disabled():
        reason = openai_disabled_reason()
        suffix = f" ({reason})" if reason else ""
        raise EnvironmentError(f"{feature}는 현재 프로젝트 정책상 비활성화되어 있습니다{suffix}.")
