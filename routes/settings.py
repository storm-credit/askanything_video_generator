"""설정·헬스체크·관리 라우터.

/api/engines, /api/key-usage, /api/health, /api/model-limits,
/api/cancel, /api/status, /api/bgm-themes, /api/channels,
/api/settings/add-env-key, /api/settings/remove-env-key,
/api/health/quota, /api/admin/quota/reset
"""

from __future__ import annotations

import os

from fastapi import APIRouter, Query

from routes.shared import (
    cancel_events,
    active_generation_ids,
    generation_lock,
)

router = APIRouter(prefix="/api", tags=["settings"])


# ── 엔진 / 키 사용량 ─────────────────────────────────────────────


@router.get("/engines")
async def list_engines():
    from modules.video.engines import get_available_engines
    return get_available_engines()


@router.get("/key-usage")
async def key_usage():
    """Google API 키별 사용량 통계 (세션 내 추적)."""
    from modules.utils.keys import get_key_usage_stats, count_google_keys
    stats = get_key_usage_stats()
    return {
        "total_keys": count_google_keys(),
        "keys": stats,
        "note": "서버 재시작 시 카운터가 초기화됩니다. Veo 3는 유료 계정 기준 일일 한도가 있습니다.",
    }


# ── 헬스체크 ─────────────────────────────────────────────────────


@router.get("/health")
async def health_check():
    """각 API 키의 설정 상태를 개별적으로 반환합니다."""

    def _is_set(val: str | None, placeholders: list[str] | None = None) -> bool:
        if not val or not val.strip():
            return False
        for ph in (placeholders or []):
            if val.startswith(ph) or val == ph:
                return False
        return True

    openai_key = os.getenv("OPENAI_API_KEY", "")
    elevenlabs_key = os.getenv("ELEVENLABS_API_KEY", "")
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    gemini_keys = os.getenv("GEMINI_API_KEYS", "")
    claude_key = os.getenv("ANTHROPIC_API_KEY", "")
    kling_ak = os.getenv("KLING_ACCESS_KEY", "")
    kling_sk = os.getenv("KLING_SECRET_KEY", "")
    tavily_key = os.getenv("TAVILY_API_KEY", "")

    def _mask(val: str) -> str:
        if not val or len(val) <= 8:
            return "****"
        return val[:4] + "***" + val[-4:]

    keys = {
        "openai": _is_set(openai_key, ["sk-proj-YOUR"]),
        "elevenlabs": _is_set(elevenlabs_key, ["YOUR_ELEVENLABS_API_KEY_HERE"]),
        "gemini": _is_set(gemini_key) or _is_set(gemini_keys),
        "claude_key": _is_set(claude_key),
        "kling_access": _is_set(kling_ak, ["YOUR"]),
        "kling_secret": _is_set(kling_sk, ["YOUR"]),
        "tavily": _is_set(tavily_key),
    }

    # 마스킹된 키 목록 (프론트엔드 표시용)
    from modules.utils.keys import get_all_google_keys, mask_key, count_google_keys
    all_google = get_all_google_keys()
    masked_keys = {
        "openai": [_mask(openai_key)] if _is_set(openai_key, ["sk-proj-YOUR"]) else [],
        "elevenlabs": [_mask(elevenlabs_key)] if _is_set(elevenlabs_key, ["YOUR_ELEVENLABS_API_KEY_HERE"]) else [],
        "gemini": [mask_key(k) for k in all_google] if all_google else [],
        "claude_key": [_mask(claude_key)] if _is_set(claude_key) else [],
        "kling_access": [_mask(kling_ak)] if _is_set(kling_ak, ["YOUR"]) else [],
        "kling_secret": [_mask(kling_sk)] if _is_set(kling_sk, ["YOUR"]) else [],
        "tavily": [_mask(tavily_key)] if _is_set(tavily_key) else [],
    }

    missing = [k for k, v in keys.items() if not v]
    google_key_count = count_google_keys()
    return {
        "status": "ok" if not missing else "missing_keys",
        "keys": keys,
        "missing": missing,
        "masked_keys": masked_keys,
        "google_key_count": google_key_count,
    }


# ── 모델 제한 ────────────────────────────────────────────────────


@router.get("/model-limits")
async def model_limits():
    """모델별 Rate Limit + 잔여 호출 수를 반환합니다."""
    from modules.utils.keys import get_service_usage_totals, count_google_keys
    from modules.utils.models import MODEL_RATE_LIMITS
    usage_totals = get_service_usage_totals()
    num_keys = max(count_google_keys(), 1)

    # 서비스 이름 → 모델 ID 매핑 (Google 모델)
    service_map = {
        "gemini": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
        "imagen": ["imagen-4.0-generate-001", "imagen-4.0-fast-generate-001"],
        "veo3": ["veo-3.0-generate-001", "veo-3.0-fast-generate-001"],
    }

    result = {}
    for model_id, limits in MODEL_RATE_LIMITS.items():
        used = 0
        total_rpd = limits["rpd"]
        # Google 모델: 키 수 × RPD, 사용량은 서비스 단위 합산
        for svc, model_ids in service_map.items():
            if model_id in model_ids:
                used = usage_totals.get(svc, 0)
                total_rpd = limits["rpd"] * num_keys
                break
        remaining = max(total_rpd - used, 0)
        result[model_id] = {**limits, "used": used, "total_rpd": total_rpd, "remaining": remaining}

    return result


# ── 키 검증 유틸리티 ──────────────────────────────────────────────


def _validate_keys(api_key_override: str | None, elevenlabs_key_override: str | None, video_engine: str,
                    image_engine: str = "imagen", llm_provider: str = "gemini", llm_key_override: str | None = None) -> list[str]:
    """파이프라인 시작 전 필수 키 검증. 누락된 키 이름 목록을 반환."""
    from modules.utils.keys import get_google_key
    errors = []

    # OpenAI 키: DALL-E/GPT/Sora2 선택 시 필수, Whisper 자막은 경고만
    openai_key = api_key_override or os.getenv("OPENAI_API_KEY", "")
    openai_missing = not openai_key or openai_key.startswith("sk-proj-YOUR")
    openai_needed_for = []
    if llm_provider == "openai":
        openai_needed_for.append("GPT 기획")
    if image_engine == "dalle":
        openai_needed_for.append("DALL-E 이미지")
    if video_engine == "sora2":
        openai_needed_for.append("Sora2 비디오")

    if openai_missing and openai_needed_for:
        openai_needed_for.append("Whisper 자막")
        errors.append(f"OPENAI_API_KEY ({' + '.join(openai_needed_for)}에 필수)")
    elif openai_missing:
        # Whisper만 필요 — Gemini 기반 구성에서는 경고만 (자막 없이 진행 가능)
        print("  [경고] OPENAI_API_KEY 미설정 — Whisper 자막 타임스탬프 사용 불가")

    # Imagen / Nano Banana 사용 시 Google 키 필요
    if image_engine in ("imagen", "nano_banana"):
        gemini_key = llm_key_override or os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
        if not gemini_key:
            errors.append("GEMINI_API_KEY (이미지 생성에 필수)")

    # LLM 프로바이더별 키 검증
    if llm_provider == "gemini":
        gemini_key = llm_key_override or os.getenv("GEMINI_API_KEY", "")
        if not gemini_key:
            errors.append("GEMINI_API_KEY (Gemini 기획 엔진에 필수)")
    elif llm_provider == "claude":
        claude_key = llm_key_override or os.getenv("ANTHROPIC_API_KEY", "")
        if not claude_key:
            errors.append("ANTHROPIC_API_KEY (Claude 기획 엔진에 필수)")

    elevenlabs_key = elevenlabs_key_override or os.getenv("ELEVENLABS_API_KEY", "")
    if not elevenlabs_key or elevenlabs_key == "YOUR_ELEVENLABS_API_KEY_HERE":
        errors.append("ELEVENLABS_API_KEY (TTS 음성 생성에 필수)")

    # Veo 3: Google API 직접 연동 (GEMINI_API_KEYS 로테이션)
    if video_engine == "veo3":
        google_key = llm_key_override or get_google_key() or ""
        if not google_key:
            errors.append("GEMINI_API_KEY 또는 GEMINI_API_KEYS (Veo 3 비디오 엔진에 필수)")

    # Kling: 직접 API
    if video_engine == "kling":
        kling_ak = os.getenv("KLING_ACCESS_KEY", "")
        if not kling_ak or kling_ak.startswith("YOUR"):
            errors.append("KLING_ACCESS_KEY (Kling 비디오 엔진에 필수)")

    if video_engine == "sora2":
        openai_check = api_key_override or os.getenv("OPENAI_API_KEY", "")
        if not openai_check or openai_check.startswith("sk-proj-YOUR"):
            errors.append("OPENAI_API_KEY (Sora 2 비디오 엔진에 필수)")

    return errors


# ── 취소 / 상태 ──────────────────────────────────────────────────


@router.post("/cancel")
async def cancel_generation(generation_id: str | None = Query(None)):
    """진행 중인 생성 작업을 취소합니다. generation_id 지정 시 해당 작업만, 미지정 시 모든 작업 취소."""
    with generation_lock:
        if generation_id:
            if generation_id in cancel_events:
                cancel_events[generation_id][0].set()
                print(f"[취소] 생성 작업 취소 요청: {generation_id}")
                return {"status": "cancelled", "generation_id": generation_id}
            return {"status": "not_found", "message": f"작업 {generation_id}을 찾을 수 없습니다."}
        # generation_id 미지정: 모든 활성 작업 취소
        cancelled = []
        for gid in list(active_generation_ids):
            if gid in cancel_events:
                cancel_events[gid][0].set()
                cancelled.append(gid)
        if cancelled:
            print(f"[취소] 모든 작업 취소: {cancelled}")
            return {"status": "cancelled", "generation_ids": cancelled}
        return {"status": "idle", "message": "진행 중인 생성 작업이 없습니다."}


@router.get("/status")
async def generation_status():
    """현재 생성 상태 확인."""
    with generation_lock:
        return {
            "active": len(active_generation_ids) > 0,
            "generation_ids": list(active_generation_ids),
            "count": len(active_generation_ids),
        }


# ── BGM / 채널 프리셋 ────────────────────────────────────────────


@router.get("/bgm-themes")
async def bgm_themes():
    themes = ["random", "none"]
    bgm_dir = os.path.join("brand", "bgm")
    if os.path.isdir(bgm_dir):
        for f in sorted(os.listdir(bgm_dir)):
            if f.lower().endswith(('.mp3', '.wav', '.m4a')):
                themes.append(os.path.splitext(f)[0].lower())
    elif os.path.exists(os.path.join("brand", "bgm.mp3")):
        themes = ["random", "none"]  # 단일 파일만 있으면 random = 그 파일
    return {"themes": themes}


@router.get("/channels")
async def list_channels():
    """등록된 채널 목록 및 프리셋 반환."""
    from modules.utils.channel_config import get_channel_names, get_channel_preset
    channels = {}
    for name in get_channel_names():
        preset = get_channel_preset(name)
        if preset:
            channels[name] = {k: v for k, v in preset.items() if k != "voice_id"}
    return {"channels": channels}


@router.put("/channels/{name}")
async def upsert_channel(name: str, body: dict):
    """채널 프리셋 추가/수정 (런타임 전용, 재시작 시 channel_config.py 기준 초기화)."""
    from modules.utils.channel_config import CHANNEL_PRESETS
    allowed = {"language", "platforms", "tts_speed", "caption_size", "caption_y", "visual_style", "tone", "upload_accounts", "keyword_tags", "voice_settings", "camera_style"}
    filtered = {k: v for k, v in body.items() if k in allowed}
    if name in CHANNEL_PRESETS:
        CHANNEL_PRESETS[name].update(filtered)
    else:
        CHANNEL_PRESETS[name] = {
            "voice_id": "pNInz6obpgDQGcFmaJgB",
            "bgm_theme": "random",
            **filtered,
        }
    return {"status": "ok", "channel": name}


# ── 환경 키 관리 ─────────────────────────────────────────────────


@router.post("/settings/add-env-key")
async def add_env_key(req: dict):
    """프론트에서 키 추가 → .env에 저장."""
    key_type = req.get("keyType", "gemini")
    new_key = req.get("key", "").strip()
    if not new_key:
        return {"ok": False, "error": "키가 비어있음"}

    env_var_map = {"gemini": "GEMINI_API_KEYS", "openai": "OPENAI_API_KEY", "elevenlabs": "ELEVENLABS_API_KEY"}
    env_var = env_var_map.get(key_type, "GEMINI_API_KEYS")

    env_path = "/app/.env"
    if not os.path.exists(env_path):
        env_path = os.path.join(os.path.dirname(__file__), "..", ".env")

    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    found = False
    new_lines = []
    for line in lines:
        if line.startswith(f"{env_var}="):
            existing = line.strip().split("=", 1)[1]
            keys = [k.strip() for k in existing.split(",") if k.strip()]
            if new_key not in keys:
                keys.append(new_key)
            new_lines.append(f"{env_var}={','.join(keys)}\n")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{env_var}={new_key}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    # 환경변수도 즉시 갱신
    current = os.getenv(env_var, "")
    if new_key not in current:
        os.environ[env_var] = f"{current},{new_key}".strip(",")

    masked = f"...{new_key[-4:]}"
    print(f"[키 추가] {env_var}에 {masked} 추가됨")
    return {"ok": True, "masked": masked}


@router.post("/settings/remove-env-key")
async def remove_env_key(req: dict):
    """프론트엔드에서 .env 키 제거."""
    key_type = req.get("keyType", "gemini")
    masked = req.get("maskedKey", "")

    env_var_map = {"gemini": "GEMINI_API_KEYS", "openai": "OPENAI_API_KEY", "elevenlabs": "ELEVENLABS_API_KEY"}
    env_var = env_var_map.get(key_type, "GEMINI_API_KEYS")

    # .env 파일 읽기 (도커 볼륨 마운트 경로 또는 로컬)
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if not os.path.exists(env_path):
        # 도커 환경: 볼륨 마운트된 경로 시도
        for p in ["/app/.env", os.path.join(os.getcwd(), ".env")]:
            if os.path.exists(p):
                env_path = p
                break
    if not os.path.exists(env_path):
        return {"ok": False, "error": ".env 파일 없음"}

    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # 키 매칭 (마스킹된 키에서 앞뒤 일부로 매칭)
    new_lines = []
    removed = 0
    for line in lines:
        if line.startswith(f"{env_var}="):
            keys = line.strip().split("=", 1)[1].split(",")
            # 마스킹 패턴 유연 매칭: 프론트가 보내는 형식에 관계없이 앞/뒤 글자로 매칭
            filtered = []
            for k in keys:
                k = k.strip()
                if not k:
                    continue
                # 여러 마스킹 길이로 매칭 시도 (앞6~10 + 뒤2~4)
                matched = False
                for prefix_len in range(6, min(len(k), 12)):
                    for suffix_len in range(2, min(len(k) - prefix_len, 5)):
                        candidate = k[:prefix_len] + "***" + k[-suffix_len:]
                        if candidate == masked:
                            matched = True
                            break
                    if matched:
                        break
                # 추가: "AIza ... R7ko" 같은 공백 포함 형식도 매칭
                if not matched and "..." in masked:
                    parts = masked.replace(" ", "").split("...")
                    if len(parts) == 2 and k.startswith(parts[0]) and k.endswith(parts[1]):
                        matched = True
                if matched:
                    removed += 1
                    key_masked = f"...{k[-4:]}"
                    print(f"[키 제거] {key_masked} 제거됨")
                else:
                    filtered.append(k)
            if filtered:
                new_lines.append(f"{env_var}={','.join(filtered)}\n")
            else:
                new_lines.append(f"{env_var}=\n")
        else:
            new_lines.append(line)

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    return {"ok": True, "removed": removed}


# ── 쿼터 관리 ────────────────────────────────────────────────────


@router.get("/health/quota")
async def quota_health():
    """프로젝트 쿼터 상태 확인."""
    from modules.utils.project_quota import quota_manager
    return {
        "project_count": len(quota_manager.projects),
        "projects": quota_manager.get_status(),
    }


@router.post("/admin/quota/reset/{project_name}")
async def reset_project_quota(project_name: str):
    """수동 프로젝트 차단 해제."""
    from modules.utils.project_quota import quota_manager
    quota_manager.reset_project(project_name)
    return {"ok": True, "project": project_name}
