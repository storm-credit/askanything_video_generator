"""API key validation logic — extracted from generate.py."""

import os


def validate_keys(
    api_key_override: str | None,
    elevenlabs_key_override: str | None,
    video_engine: str,
    image_engine: str = "imagen",
    llm_provider: str = "gemini",
    llm_key_override: str | None = None,
) -> list[str]:
    """파이프라인 시작 전 필수 키 검증. 누락된 키 이름 목록을 반환."""
    from modules.utils.keys import get_google_key
    from modules.utils.provider_policy import get_openai_api_key, is_openai_api_disabled

    # Vertex AI SA키 환경이면 GEMINI_API_KEY 없어도 OK
    _is_vertex = bool(os.getenv("GOOGLE_APPLICATION_CREDENTIALS")) or os.getenv("GEMINI_BACKEND") == "vertex_ai"

    errors = []

    # OpenAI 키: DALL-E/GPT/Sora2 선택 시 필수, Whisper 자막은 경고만
    openai_key = get_openai_api_key(api_key_override)
    openai_missing = not openai_key or openai_key.startswith("sk-proj-YOUR")
    openai_needed_for = []
    if llm_provider == "openai":
        openai_needed_for.append("GPT 기획")
    if image_engine == "dalle":
        openai_needed_for.append("DALL-E 이미지")
    if video_engine == "sora2":
        openai_needed_for.append("Sora2 비디오")

    if openai_needed_for and is_openai_api_disabled():
        errors.append(f"OpenAI API 비활성화 ({' + '.join(openai_needed_for)} 사용 불가)")
    elif openai_missing and openai_needed_for:
        openai_needed_for.append("Whisper 자막")
        errors.append(f"OPENAI_API_KEY ({' + '.join(openai_needed_for)}에 필수)")
    elif openai_missing and not is_openai_api_disabled():
        print("  [경고] OPENAI_API_KEY 미설정 — Whisper 자막 타임스탬프 사용 불가")

    # Imagen / Nano Banana 사용 시 Google 키 필요 (Vertex SA키면 스킵)
    if image_engine in ("imagen", "nano_banana") and not _is_vertex:
        gemini_key = llm_key_override or os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "") or get_google_key()
        if not gemini_key:
            errors.append("GEMINI_API_KEY (이미지 생성에 필수)")

    # LLM 프로바이더별 키 검증 (Vertex SA키면 스킵)
    if llm_provider == "gemini" and not _is_vertex:
        gemini_key = llm_key_override or os.getenv("GEMINI_API_KEY", "") or get_google_key()
        if not gemini_key:
            errors.append("GEMINI_API_KEY (Gemini 기획 엔진에 필수)")
    elif llm_provider == "claude":
        claude_key = llm_key_override or os.getenv("ANTHROPIC_API_KEY", "")
        if not claude_key:
            errors.append("ANTHROPIC_API_KEY (Claude 기획 엔진에 필수)")

    # Qwen3 TTS 엔진 사용 시 ElevenLabs 키 불필요
    _tts_engine = os.getenv("TTS_ENGINE", "qwen3").lower()
    if _tts_engine != "qwen3":
        elevenlabs_key = elevenlabs_key_override or os.getenv("ELEVENLABS_API_KEY", "")
        if not elevenlabs_key or elevenlabs_key == "YOUR_ELEVENLABS_API_KEY_HERE":
            errors.append("ELEVENLABS_API_KEY (TTS 음성 생성에 필수)")

    # Veo 3: Google API 직접 연동 (Vertex SA키면 스킵)
    if video_engine == "veo3" and not _is_vertex:
        google_key = llm_key_override or get_google_key() or ""
        if not google_key:
            errors.append("GEMINI_API_KEY 또는 GEMINI_API_KEYS (Veo 3 비디오 엔진에 필수)")

    # Kling: 직접 API
    if video_engine == "kling":
        kling_ak = os.getenv("KLING_ACCESS_KEY", "")
        if not kling_ak or kling_ak.startswith("YOUR"):
            errors.append("KLING_ACCESS_KEY (Kling 비디오 엔진에 필수)")

    if video_engine == "sora2" and not is_openai_api_disabled():
        openai_check = get_openai_api_key(api_key_override)
        if not openai_check or openai_check.startswith("sk-proj-YOUR"):
            errors.append("OPENAI_API_KEY (Sora 2 비디오 엔진에 필수)")

    return errors
