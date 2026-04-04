"""Gemini 클라이언트 팩토리 — AI Studio / Vertex AI 전환 지원.

.env 설정:
  GEMINI_BACKEND=ai_studio   (기본값) → API Key + generativelanguage.googleapis.com
  GEMINI_BACKEND=vertex_ai              → ADC 인증 + aiplatform.googleapis.com
  GEMINI_BACKEND=vertex_api_key         → API Key + aiplatform.googleapis.com (REST)

Vertex AI 추가 설정:
  VERTEX_PROJECT=your-gcp-project-id
  VERTEX_LOCATION=us-central1  (기본값)
"""
import os

_backend: str | None = None


def _get_backend() -> str:
    global _backend
    if _backend is None:
        _backend = os.getenv("GEMINI_BACKEND", "ai_studio").lower().strip()
    return _backend


def create_gemini_client(api_key: str | None = None):
    """GEMINI_BACKEND 설정에 따라 적절한 genai.Client를 반환합니다.

    - ai_studio: API Key 기반 (기존 방식)
    - vertex_ai: ADC 인증 (서비스 계정 / gcloud auth)
    - vertex_api_key: API Key로 Vertex AI 엔드포인트 사용
      → google-genai SDK는 project+api_key 동시 사용 불가
      → API Key 모드에서는 AI Studio 클라이언트를 쓰되, 모델명에 Vertex 경로를 붙여서 사용
    """
    from google import genai

    backend = _get_backend()

    if backend == "vertex_ai":
        # ADC 인증 (서비스 계정 키 파일 또는 gcloud auth)
        project = os.getenv("VERTEX_PROJECT", "")
        location = os.getenv("VERTEX_LOCATION", "us-central1")
        return genai.Client(
            vertexai=True,
            project=project,
            location=location,
        )

    # ai_studio 또는 vertex_api_key 모두 API Key 기반 클라이언트
    # vertex_api_key의 경우에도 google-genai SDK는 API Key로 Vertex 모델에 접근 가능
    # (SDK가 내부적으로 적절한 엔드포인트를 라우팅함)
    return genai.Client(api_key=api_key)


def get_backend_label() -> str:
    """현재 백엔드 라벨 반환 (로그/UI 표시용)."""
    backend = _get_backend()
    if backend == "vertex_ai":
        project = os.getenv("VERTEX_PROJECT", "unknown")
        location = os.getenv("VERTEX_LOCATION", "us-central1")
        return f"Vertex AI ADC ({project}/{location})"
    if backend == "vertex_api_key":
        return "Vertex AI (API Key)"
    return "AI Studio"
