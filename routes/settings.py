"""설정·헬스체크·관리 라우터.

/api/engines, /api/key-usage, /api/health, /api/model-limits,
/api/cancel, /api/status, /api/bgm-themes, /api/channels,
/api/settings/add-env-key, /api/settings/remove-env-key,
/api/settings/billing, /api/settings/billing/check,
/api/health/quota, /api/admin/quota/reset
"""

from __future__ import annotations

import os
import requests

from fastapi import APIRouter, Query, UploadFile, File, HTTPException

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
    def _candidate_qwen3_urls() -> list[str]:
        configured = os.getenv("QWEN3_TTS_URL", "http://localhost:8010").strip() or "http://localhost:8010"
        urls = [configured, "http://localhost:8010", "http://host.docker.internal:8010", "http://tts:8010"]
        seen: set[str] = set()
        result: list[str] = []
        for raw in urls:
            url = raw.rstrip("/")
            if not url or url in seen:
                continue
            seen.add(url)
            result.append(url)
        return result

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
    is_vertex_backend = os.getenv("GEMINI_BACKEND") == "vertex_ai"
    vertex_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    try:
        from modules.utils.vertex_sa_manager import list_service_accounts
        vertex_sa_count = len([sa for sa in list_service_accounts() if sa.get("enabled")])
    except Exception:
        vertex_sa_count = 0
    vertex_ready = bool(is_vertex_backend and (vertex_creds.strip() or vertex_sa_count > 0))
    tts_engine = os.getenv("TTS_ENGINE", "qwen3").strip().lower() or "qwen3"
    qwen_tts_url = os.getenv("QWEN3_TTS_URL", "http://localhost:8010").strip() or "http://localhost:8010"
    qwen_tts_health = {"ok": False, "status_code": None, "url": qwen_tts_url}
    if tts_engine == "qwen3":
        for candidate_url in _candidate_qwen3_urls():
            try:
                resp = requests.get(f"{candidate_url}/health", timeout=3)
                qwen_tts_health = {
                    "ok": resp.ok,
                    "status_code": resp.status_code,
                    "url": candidate_url,
                }
                if resp.ok:
                    break
            except Exception:
                qwen_tts_health = {"ok": False, "status_code": None, "url": candidate_url}

    next_sa = None
    try:
        from modules.utils.vertex_sa_manager import get_next_service_account
        next_sa = get_next_service_account()
    except Exception:
        next_sa = None

    def _mask(val: str) -> str:
        if not val or len(val) <= 8:
            return "****"
        return val[:4] + "***" + val[-4:]

    keys = {
        "openai": _is_set(openai_key, ["sk-proj-YOUR"]),
        "elevenlabs": _is_set(elevenlabs_key, ["YOUR_ELEVENLABS_API_KEY_HERE"]),
        "gemini": _is_set(gemini_key) or _is_set(gemini_keys) or vertex_ready,
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
        "vertex_sa_count": vertex_sa_count,
        "tts": {
            "engine": tts_engine,
            "qwen_ready": bool(qwen_tts_health["ok"]),
            "qwen_status_code": qwen_tts_health["status_code"],
            "qwen_url": qwen_tts_health["url"],
            "elevenlabs_ready": keys["elevenlabs"],
        },
        "vertex": {
            "backend": os.getenv("GEMINI_BACKEND", "gemini_api"),
            "sa_only": os.getenv("VERTEX_SA_ONLY", "false").lower() in {"1", "true", "yes", "on"},
            "next_account": next_sa,
        },
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
        "veo3": [
            "veo-3.1-generate-001",
            "veo-3.1-fast-generate-001",
            "veo-3.0-generate-001",
            "veo-3.0-fast-generate-001",
        ],
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
    is_vertex_backend = os.getenv("GEMINI_BACKEND") == "vertex_ai"

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
    if image_engine in ("imagen", "nano_banana") and not is_vertex_backend:
        gemini_key = llm_key_override or os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
        if not gemini_key:
            errors.append("GEMINI_API_KEY (이미지 생성에 필수)")

    # LLM 프로바이더별 키 검증
    if llm_provider == "gemini" and not is_vertex_backend:
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
    if video_engine == "veo3" and not is_vertex_backend:
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


def _resolve_env_path() -> str | None:
    """실제 .env 파일 경로를 찾습니다."""
    candidates = [
        "/app/.env",
        os.path.join(os.path.dirname(__file__), "..", ".env"),
        os.path.join(os.getcwd(), ".env"),
    ]
    for path in candidates:
        normalized = os.path.normpath(path)
        if os.path.exists(normalized):
            return normalized
    return None


def _get_env_vars_for_key_type(key_type: str) -> list[str]:
    """키 타입별로 실제 저장될 수 있는 환경변수 후보를 반환합니다."""
    if key_type == "gemini":
        return ["GEMINI_API_KEYS", "GEMINI_API_KEY", "GOOGLE_API_KEY"]
    if key_type == "openai":
        return ["OPENAI_API_KEY"]
    if key_type == "elevenlabs":
        return ["ELEVENLABS_API_KEY"]
    return ["GEMINI_API_KEYS"]


def _masked_key_matches(raw_key: str, masked: str) -> bool:
    """프론트에서 표시된 마스킹 문자열과 실제 키가 같은지 판별합니다."""
    from modules.utils.keys import mask_key

    key = (raw_key or "").strip()
    target = (masked or "").strip().replace(" ", "")
    if not key or not target:
        return False

    # 현재 서버가 사용하는 표준 마스킹 형식 우선 비교
    if mask_key(key) == target:
        return True

    # 과거/보조 형식 호환: prefix***suffix 또는 prefix...suffix
    for divider in ("***", "..."):
        if divider in target:
            prefix, suffix = target.split(divider, 1)
            if prefix and suffix and key.startswith(prefix) and key.endswith(suffix):
                return True

    return False


def _split_env_keys(value: str) -> list[str]:
    return [k.strip() for k in (value or "").split(",") if k.strip()]


def _remove_masked_key_from_value(value: str, masked: str) -> tuple[list[str], list[str]]:
    """쉼표 구분 값에서 마스킹된 키와 일치하는 항목을 제거합니다."""
    kept: list[str] = []
    removed: list[str] = []
    for key in _split_env_keys(value):
        if _masked_key_matches(key, masked):
            removed.append(key)
        else:
            kept.append(key)
    return kept, removed


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
    env_vars = _get_env_vars_for_key_type(key_type)
    removed_keys: set[str] = set()

    # 1) .env 파일에서 제거
    env_path = _resolve_env_path()
    if env_path and os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        new_lines = []
        for line in lines:
            matched_var = next((env_var for env_var in env_vars if line.startswith(f"{env_var}=")), None)
            if not matched_var:
                new_lines.append(line)
                continue

            raw_value = line.strip().split("=", 1)[1] if "=" in line else ""
            kept, removed = _remove_masked_key_from_value(raw_value, masked)
            removed_keys.update(removed)
            new_lines.append(f"{matched_var}={','.join(kept)}\n" if kept else f"{matched_var}=\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

    # 2) 실행 중 프로세스 환경변수에서도 제거
    for env_var in env_vars:
        current = os.getenv(env_var, "")
        if not current:
            continue
        kept, removed = _remove_masked_key_from_value(current, masked)
        if removed:
            removed_keys.update(removed)
            os.environ[env_var] = ",".join(kept)

    if removed_keys:
        from modules.utils.keys import mask_key
        for raw in removed_keys:
            print(f"[키 제거] {mask_key(raw)} 제거됨")

    return {
        "ok": True,
        "removed": len(removed_keys),
        "updatedVars": env_vars,
    }


# ── Vertex AI Service Account 관리 ───────────────────────────────


@router.get("/settings/vertex-sa")
async def get_vertex_service_accounts():
    """Vertex AI SA 목록. 키 본문은 절대 반환하지 않습니다."""
    from modules.utils.vertex_sa_manager import (
        get_next_service_account,
        list_service_accounts,
    )
    from modules.utils.gemini_client import get_sa_runtime_state

    accounts = list_service_accounts()
    runtime_by_path = {item["path"]: item for item in get_sa_runtime_state()}
    enriched_accounts = []
    for account in accounts:
        runtime = runtime_by_path.get(account["path"], {})
        enriched_accounts.append({
            **account,
            "is_next": bool(runtime.get("is_next")),
            "last_used": bool(runtime.get("last_used")),
            "blocked": bool(runtime.get("blocked")),
            "blocked_remaining_sec": int(runtime.get("blocked_remaining_sec", 0)),
        })
    next_account = get_next_service_account()
    return {
        "ok": True,
        "backend": os.getenv("GEMINI_BACKEND", "ai_studio"),
        "sa_only": os.getenv("VERTEX_SA_ONLY", "").strip().lower() in {"1", "true", "yes", "on"},
        "accounts": enriched_accounts,
        "enabled_count": len([item for item in accounts if item.get("enabled")]),
        "next_account": next_account,
    }


@router.post("/settings/vertex-sa/upload")
async def upload_vertex_service_account(file: UploadFile = File(...)):
    """드래그앤드롭으로 업로드한 Vertex AI service-account JSON 저장."""
    from modules.utils.vertex_sa_manager import upload_service_account
    if not file.filename or not file.filename.lower().endswith(".json"):
        raise HTTPException(status_code=400, detail="JSON 파일만 업로드할 수 있습니다")
    raw = await file.read()
    if len(raw) > 1024 * 1024:
        raise HTTPException(status_code=400, detail="SA JSON 파일이 너무 큽니다")
    try:
        account = upload_service_account(file.filename, raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, "account": account}


@router.put("/settings/vertex-sa")
async def update_vertex_service_accounts(req: dict):
    """SA 순서/활성 상태 저장. 순서대로 한 번씩 로테이션됩니다."""
    from modules.utils.vertex_sa_manager import update_service_accounts
    items = req.get("accounts") or req.get("items") or []
    if not isinstance(items, list):
        raise HTTPException(status_code=400, detail="accounts 배열이 필요합니다")
    return {"ok": True, **update_service_accounts(items)}


@router.delete("/settings/vertex-sa/{item_id}")
async def delete_vertex_service_account(item_id: str):
    """설정창에서 업로드한 관리 SA만 삭제."""
    from modules.utils.vertex_sa_manager import delete_service_account
    try:
        return {"ok": True, **delete_service_account(item_id)}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail="SA 파일을 찾을 수 없습니다") from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/settings/vertex-sa/test")
async def test_vertex_service_account(req: dict | None = None):
    """Vertex SA 연결 상태를 실제 Vertex API로 점검한다."""
    from modules.utils.vertex_sa_manager import test_service_account

    item_id = ""
    if isinstance(req, dict):
        item_id = str(req.get("item_id") or "").strip()

    try:
        return test_service_account(item_id or None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail="Vertex 연결 테스트 중 오류가 발생했습니다") from e


# ── 청구 금액 알림 설정 ───────────────────────────────────────────


@router.get("/settings/billing")
async def get_billing_settings():
    """청구 금액 임계치 알림 설정 조회."""
    from modules.utils.cost_tracker import load_billing_settings, get_billing_overview
    return {"ok": True, "settings": load_billing_settings(), "overview": get_billing_overview()}


@router.put("/settings/billing")
async def put_billing_settings(req: dict):
    """청구 금액 임계치 알림 설정 저장."""
    from modules.utils.cost_tracker import save_billing_settings
    settings = save_billing_settings(req)
    try:
        from modules.scheduler.cron import set_hourly

        def _cron_billing_threshold():
            from modules.utils.cost_tracker import check_configured_billing_threshold
            return check_configured_billing_threshold(send_telegram=True)

        set_hourly(
            "청구 금액 임계치 확인",
            int(settings.get("cron_minute", 5)),
            _cron_billing_threshold,
            enabled=bool(settings.get("cron_enabled", True)),
        )
    except Exception as e:
        print(f"[크론] 청구 금액 알림 런타임 반영 실패: {e}")
    return {"ok": True, "settings": settings}


@router.post("/settings/billing/check")
async def check_billing_settings():
    """저장된 청구 금액 기준으로 텔레그램 알림 조건을 즉시 확인."""
    from modules.utils.cost_tracker import check_configured_billing_threshold
    result = check_configured_billing_threshold(send_telegram=True)
    return {"ok": True, "result": result}


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
