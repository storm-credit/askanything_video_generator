"""준비/세션/렌더 라우터.

/api/prepare (SSE), /api/replace-image, /api/regenerate-image,
/api/register-day-session, /api/batch-generate-images,
/api/render (SSE), /api/sessions, /api/sessions/load,
/api/sessions/generate-scripts
"""

from __future__ import annotations

import os
import json
import re
import io
import copy
import asyncio
import shutil
import traceback
import threading
import glob

from pydantic import BaseModel, Field, field_validator
from fastapi import APIRouter, HTTPException, Form, File, UploadFile
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from routes.shared import (
    prepared_sessions,
    session_lock,
    cleanup_sessions,
    generate_semaphore,
    resolve_youtube_topic,
    VOICE_MAP,
    VOICE_ID_TO_NAME,
)

router = APIRouter(prefix="/api", tags=["prepare"])


# ── 상수 ──────────────────────────────────────────────────────────

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB


# ── 세션 정리 ────────────────────────────────────────────────────

def _cleanup_sessions():
    """오래된 세션 자동 정리 (메모리 누수 방지)."""
    cleanup_sessions()


# ── 음성 선택 → services/ ────────────────────────────────────────
from services.voice import auto_select_voice as _auto_select_voice


# ── Pydantic 모델 ─────────────────────────────────────────────────


class PrepareRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    apiKey: str | None = None
    llmProvider: str = "gemini"
    llmKey: str | None = None
    llmModel: str | None = None
    imageModel: str | None = None
    geminiKeys: str | None = None
    imageEngine: str = "imagen"
    language: str = "ko"
    videoEngine: str = "none"
    channel: str | None = None
    formatType: str | None = None
    referenceUrl: str | None = None
    maxCuts: int | None = None

    @field_validator("language")
    @classmethod
    def valid_language(cls, v: str) -> str:
        allowed = {"ko", "en", "de", "da", "no", "es", "fr", "pt", "it", "nl", "sv", "pl", "ru", "ja", "zh", "ar", "tr", "hi"}
        if v not in allowed:
            raise ValueError(f"지원하지 않는 언어: {v}. 허용: {allowed}")
        return v

    @field_validator("imageEngine")
    @classmethod
    def valid_image_engine(cls, v: str) -> str:
        allowed = {"imagen", "dalle"}
        if v not in allowed:
            raise ValueError(f"지원하지 않는 이미지 엔진: {v}. 허용: {allowed}")
        return v

    @field_validator("videoEngine")
    @classmethod
    def valid_video_engine(cls, v: str) -> str:
        allowed = {"veo3", "kling", "sora2", "none"}
        if v not in allowed:
            raise ValueError(f"지원하지 않는 비디오 엔진: {v}. 허용: {allowed}")
        return v

    @field_validator("llmProvider")
    @classmethod
    def valid_llm_provider(cls, v: str) -> str:
        allowed = {"gemini", "openai", "claude"}
        if v not in allowed:
            raise ValueError(f"지원하지 않는 LLM 프로바이더: {v}. 허용: {allowed}")
        return v


class RegenerateImageRequest(BaseModel):
    sessionId: str
    cutIndex: int
    model: str | None = None


class RegisterDaySessionRequest(BaseModel):
    sessionId: str
    topic: str
    channel: str = "askanything"
    cuts: list[dict]


class BatchImageRequest(BaseModel):
    sessionId: str
    model: str = "standard"


class RenderRequest(BaseModel):
    sessionId: str
    cuts: list[dict]
    apiKey: str | None = None
    llmKey: str | None = None
    geminiKeys: str | None = None
    elevenlabsKey: str | None = None
    ttsSpeed: float = 1.05
    videoEngine: str = "none"
    videoModel: str | None = None
    cameraStyle: str = "auto"
    bgmTheme: str = "random"
    formatType: str | None = None
    channel: str | None = None
    platforms: list[str] = ["youtube"]
    captionSize: int = Field(48, ge=32, le=72)
    captionY: int = Field(28, ge=10, le=50)
    outputPath: str | None = None
    voiceId: str | None = None


class LoadSessionRequest(BaseModel):
    folder: str = Field(..., min_length=1)


class GenerateScriptsRequest(BaseModel):
    folder: str = Field(..., min_length=1)
    topic: str = ""
    lang: str = "ko"
    channel: str = ""
    num_cuts: int = 8


# ── POST /api/prepare (SSE) ──────────────────────────────────────


@router.post("/prepare")
async def prepare_endpoint(req: PrepareRequest):
    """1단계: LLM 스크립트 + 이미지 생성만 수행. TTS/렌더는 하지 않음."""

    async def sse_generator():
      # lazy imports
      from modules.gpt.cutter import generate_cuts
      from modules.image.imagen import generate_image_imagen, generate_image_nano_banana
      from modules.image.dalle import generate_image as generate_image_dalle
      from modules.utils.keys import get_google_key

      # A/B 변형 + 메타데이터 안전 초기화
      cut1_ab_variants: list = []
      video_desc = ""
      video_tags: list = []
      async with generate_semaphore:
        _gemini_keys = req.geminiKeys or None
        try:
            if os.getenv("GEMINI_BACKEND") == "vertex_ai" and req.llmProvider == "gemini":
                llm_key_for_request = None
            else:
                llm_key_for_request = get_google_key(req.llmKey, extra_keys=_gemini_keys) if req.llmProvider == "gemini" else req.llmKey
            loop = asyncio.get_running_loop()

            yield {"data": "PROG|10\n"}
            # YouTube URL 자동 감지 + topic 교체
            prep_ref_url = req.referenceUrl
            prep_topic = req.topic
            old_prep_topic = prep_topic
            prep_topic, prep_ref_url = resolve_youtube_topic(prep_topic, prep_ref_url)
            if prep_topic != old_prep_topic:
                yield {"data": f"[레퍼런스 분석] YouTube 주제 추출 완료: '{prep_topic.split(chr(10))[0]}'\n"}

            yield {"data": f"[기획] '{prep_topic.split(chr(10))[0]}' 스크립트 생성 중...\n"}

            cuts, topic_folder, video_title, video_tags, video_desc, _fact_ctx = await loop.run_in_executor(
                None,
                lambda: generate_cuts(
                    prep_topic, api_key_override=req.apiKey, lang=req.language,
                    llm_provider=req.llmProvider, llm_key_override=llm_key_for_request,
                    channel=req.channel, llm_model=req.llmModel,
                    reference_url=prep_ref_url,
                    format_type=req.formatType,
                ),
            )

            # 테스트 모드: 컷 수 제한
            if req.maxCuts and len(cuts) > req.maxCuts:
                cuts = cuts[:req.maxCuts]
                yield {"data": f"[테스트 모드] {req.maxCuts}컷으로 제한\n"}

            yield {"data": "PROG|30\n"}
            yield {"data": f"[기획 완료] {len(cuts)}컷 스크립트 생성!\n"}

            # 이미지 생성
            image_label = {"imagen": "Imagen 4", "nano_banana": "Nano Banana", "dalle": "DALL-E"}.get(req.imageEngine, req.imageEngine)
            yield {"data": f"[이미지] {image_label}로 이미지 생성 중...\n"}

            image_paths = []
            for i, cut in enumerate(cuts):
                try:
                    _topic = prep_topic
                    if req.imageEngine == "imagen":
                        img_key = get_google_key(req.llmKey, service="imagen", extra_keys=_gemini_keys)
                        img_path = await loop.run_in_executor(
                            None, lambda idx=i, c=cut, k=img_key, t=_topic: generate_image_imagen(c["prompt"], idx, topic_folder, k, model_override=req.imageModel, gemini_api_keys=_gemini_keys, topic=t)
                        )
                    elif req.imageEngine == "nano_banana":
                        img_key = get_google_key(req.llmKey, service="nano_banana", extra_keys=_gemini_keys)
                        img_path = await loop.run_in_executor(
                            None, lambda idx=i, c=cut, k=img_key, t=_topic: generate_image_nano_banana(c["prompt"], idx, topic_folder, k, gemini_api_keys=_gemini_keys, topic=t)
                        )
                    else:
                        img_key = req.apiKey
                        img_path = await loop.run_in_executor(
                            None, lambda idx=i, c=cut, k=img_key, t=_topic: generate_image_dalle(c["prompt"], idx, topic_folder, k, topic=t)
                        )
                    image_paths.append(img_path)
                except Exception as exc:
                    # 폴백 체인
                    if req.imageEngine in ("imagen", "nano_banana"):
                        fallback_from = image_label
                        # Imagen → Nano Banana 폴백
                        if req.imageEngine == "imagen":
                            print(f"[컷 {i+1} Imagen 실패 → Nano Banana 폴백] {exc}")
                            yield {"data": f"  -> 컷 {i+1} Imagen 실패, Nano Banana로 폴백\n"}
                            try:
                                _nb_key = get_google_key(req.llmKey, service="nano_banana", extra_keys=_gemini_keys)
                                _topic2 = prep_topic
                                img_path = await loop.run_in_executor(
                                    None, lambda idx=i, c=cut, k=_nb_key, t=_topic2: generate_image_nano_banana(c["prompt"], idx, topic_folder, k, topic=t)
                                )
                                image_paths.append(img_path)
                                continue
                            except Exception as nb_exc:
                                print(f"[컷 {i+1} Nano Banana 실패 → DALL-E 폴백] {nb_exc}")
                                yield {"data": f"  -> 컷 {i+1} Nano Banana 실패, DALL-E로 폴백\n"}
                        else:
                            print(f"[컷 {i+1} Nano Banana 실패 → DALL-E 폴백] {exc}")
                            yield {"data": f"  -> 컷 {i+1} Nano Banana 실패, DALL-E로 폴백\n"}
                        # DALL-E 폴백
                        _dalle_key = req.apiKey or os.getenv("OPENAI_API_KEY")
                        if _dalle_key:
                            try:
                                _topic2 = prep_topic
                                img_path = await loop.run_in_executor(
                                    None, lambda idx=i, c=cut, k=_dalle_key, t=_topic2: generate_image_dalle(c["prompt"], idx, topic_folder, k, topic=t)
                                )
                                image_paths.append(img_path)
                            except Exception as dalle_exc:
                                print(f"[컷 {i+1} DALL-E 폴백도 실패] {dalle_exc}")
                                image_paths.append(None)
                        else:
                            image_paths.append(None)
                    else:
                        print(f"[컷 {i+1} 이미지 실패] {exc}")
                        image_paths.append(None)

                prog = 30 + int(60 * ((i + 1) / len(cuts)))
                yield {"data": f"PROG|{prog}\n"}
                yield {"data": f"  -> 컷 {i+1}/{len(cuts)} 이미지 생성 완료\n"}

            try:
                from modules.utils.cost_tracker import record_asset_cost

                image_success_count = sum(1 for p in image_paths if p and os.path.exists(p))
                if image_success_count:
                    record_asset_cost(
                        channel=req.channel or "unknown",
                        image_count=image_success_count + len(cut1_ab_variants),
                    )
            except Exception as cost_exc:
                print(f"[비용 추적] 이미지 비용 기록 실패(무시): {cost_exc}")

            # 세션 저장 (오래된 세션 자동 정리)
            import uuid as _uuid
            import time as _time
            _cleanup_sessions()
            session_id = _uuid.uuid4().hex
            with session_lock:
                prepared_sessions[session_id] = {
                    "cuts": cuts,
                    "topic_folder": topic_folder,
                    "title": video_title,
                    "description": video_desc,
                    "tags": video_tags,
                    "image_paths": image_paths,
                    "topic": req.topic,
                    "channel": req.channel or "",
                    "language": req.language,
                    "cut1_ab_variants": cut1_ab_variants,
                    "_created": _time.time(),
                }

            # cuts.json 자동 저장 (세션 복원용)
            cuts_json_path = os.path.join("assets", topic_folder, "cuts.json")
            try:
                os.makedirs(os.path.dirname(cuts_json_path), exist_ok=True)
                with open(cuts_json_path, "w", encoding="utf-8") as _f:
                    json.dump({
                        "cuts": cuts,
                        "title": video_title,
                        "tags": video_tags,
                        "metadata": {
                            "topic": req.topic,
                            "channel": req.channel or "",
                            "language": req.language,
                            "created_at": __import__("datetime").datetime.now().isoformat(),
                        }
                    }, _f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"[세션 저장] cuts.json 저장 실패: {e}")

            # 미리보기 데이터 전송
            preview_cuts = []
            for i, cut in enumerate(cuts):
                img_url = None
                if image_paths[i] and os.path.exists(image_paths[i]):
                    rel = image_paths[i].replace("\\", "/")
                    idx = rel.find("assets/")
                    if idx >= 0:
                        img_url = f"/{rel[idx:]}"
                cut_data: dict = {
                    "index": i,
                    "script": cut["script"],
                    "prompt": cut.get("prompt", ""),
                    "description": cut.get("description", ""),
                    "image_url": img_url,
                }
                # 컷1 A/B 변형 이미지 URL
                if i == 0 and cut1_ab_variants:
                    ab_urls = []
                    for vp in cut1_ab_variants:
                        if vp and os.path.exists(vp):
                            vrel = vp.replace("\\", "/")
                            vidx = vrel.find("assets/")
                            if vidx >= 0:
                                ab_urls.append(f"/{vrel[vidx:]}")
                    if ab_urls:
                        cut_data["ab_variants"] = ab_urls
                preview_cuts.append(cut_data)

            yield {"data": "PROG|100\n"}
            yield {"data": f"PREVIEW|{json.dumps({'sessionId': session_id, 'title': video_title, 'description': video_desc, 'tags': video_tags, 'cuts': preview_cuts}, ensure_ascii=False)}\n"}

        except Exception as e:
            traceback.print_exc()
            safe_msg = re.sub(r"(AIza|sk-|key=|token=|Bearer )[A-Za-z0-9_\-]{4,}", r"\1***", str(e)[:200])
            yield {"data": f"ERROR|[준비 오류] {safe_msg}\n"}

    return EventSourceResponse(sse_generator())


# ── POST /api/replace-image ──────────────────────────────────────


@router.post("/replace-image")
async def replace_image_endpoint(
    sessionId: str = Form(...),
    cutIndex: int = Form(...),
    file: UploadFile = File(...),
):
    """미리보기 단계에서 특정 컷의 이미지를 사용자 파일로 교체."""
    with session_lock:
        session = prepared_sessions.get(sessionId)
    if not session:
        return JSONResponse(status_code=404, content={"error": "세션을 찾을 수 없습니다."})

    image_paths = session.get("image_paths", [])
    if cutIndex < 0 or cutIndex >= len(image_paths):
        return JSONResponse(status_code=400, content={"error": f"잘못된 컷 인덱스: {cutIndex}"})

    # 파일 타입 검증
    if file.content_type not in ALLOWED_IMAGE_TYPES:
        return JSONResponse(status_code=400, content={"error": "PNG, JPG, WEBP 파일만 가능합니다."})

    # 파일 읽기 + 크기 검증
    data = await file.read()
    if len(data) > MAX_IMAGE_SIZE:
        return JSONResponse(status_code=400, content={"error": "파일 크기가 20MB를 초과합니다."})

    # 1080x1920 리사이즈 + 저장
    try:
        from PIL import Image, ImageOps
        img = Image.open(io.BytesIO(data)).convert("RGB")
        fitted = ImageOps.fit(img, (1080, 1920), method=Image.LANCZOS, centering=(0.5, 0.5))

        dest_path = image_paths[cutIndex]
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        import tempfile
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(dest_path), suffix=".tmp")
        os.close(fd)
        try:
            fitted.save(tmp, format="PNG")
            os.replace(tmp, dest_path)
        except Exception:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise

        # 응답: 새 이미지 URL
        rel = dest_path.replace("\\", "/")
        idx = rel.find("assets/")
        img_url = f"/{rel[idx:]}" if idx >= 0 else None
        print(f"[이미지 교체] 컷 {cutIndex + 1} 사용자 이미지로 교체 완료")
        return {"ok": True, "image_url": img_url}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"이미지 처리 실패: {str(e)}"})


# ── POST /api/regenerate-image ───────────────────────────────────


@router.post("/regenerate-image")
async def regenerate_image_endpoint(req: RegenerateImageRequest):
    """특정 컷의 이미지를 재생성합니다. 모델 지정 가능."""
    with session_lock:
        session = prepared_sessions.get(req.sessionId)
    if not session:
        return JSONResponse(status_code=404, content={"error": "세션을 찾을 수 없습니다."})

    cuts = session.get("cuts", [])
    image_paths = session.get("image_paths", [])
    if req.cutIndex < 0 or req.cutIndex >= len(cuts):
        return JSONResponse(status_code=400, content={"error": f"잘못된 컷 인덱스: {req.cutIndex}"})

    cut = cuts[req.cutIndex]
    prompt = cut.get("prompt", cut.get("image_prompt", ""))
    if not prompt:
        return JSONResponse(status_code=400, content={"error": "이미지 프롬프트가 없습니다."})

    topic_folder = session.get("topic_folder", "default_topic")
    topic = session.get("topic", "")

    # 이미지 캐시 무효화 — 같은 프롬프트로 재생성 시 캐시 히트 방지
    from modules.image.imagen import MASTER_STYLE
    from modules.utils.cache import invalidate_cache
    try:
        invalidate_cache(MASTER_STYLE + prompt)
    except Exception:
        pass  # 캐시 무효화 실패해도 진행

    gemini_keys = os.getenv("GEMINI_API_KEYS", os.getenv("GEMINI_API_KEY", ""))

    try:
        new_path = None
        model_name = req.model or "standard"

        if model_name in ("standard", "fast", "ultra"):
            model_map = {
                "standard": "imagen-4.0-generate-001",
                "fast": "imagen-4.0-fast-generate-001",
                "ultra": "imagen-4.0-ultra-generate-001",
            }
            from modules.image.imagen import generate_image_imagen
            new_path = generate_image_imagen(
                prompt, req.cutIndex, topic_folder,
                model_override=model_map[model_name],
                gemini_api_keys=gemini_keys, topic=topic,
            )
        elif model_name == "nano_banana":
            from modules.image.imagen import generate_image_nano_banana
            new_path = generate_image_nano_banana(
                prompt, req.cutIndex, topic_folder,
                gemini_api_keys=gemini_keys, topic=topic,
            )
        elif model_name == "dalle":
            from modules.image.dalle import generate_image as generate_image_dalle
            new_path = generate_image_dalle(prompt, req.cutIndex, topic_folder, topic=topic)
        else:
            return JSONResponse(status_code=400, content={"error": f"알 수 없는 모델: {model_name}"})

        if new_path and os.path.exists(new_path):
            # 세션 업데이트
            cost_channel = "unknown"
            with session_lock:
                if req.sessionId in prepared_sessions:
                    prepared_sessions[req.sessionId]["image_paths"][req.cutIndex] = new_path
                    cost_channel = prepared_sessions[req.sessionId].get("channel") or cost_channel
            try:
                from modules.utils.cost_tracker import record_asset_cost
                record_asset_cost(channel=cost_channel, image_count=1)
            except Exception as cost_exc:
                print(f"[비용 추적] 이미지 재생성 비용 기록 실패(무시): {cost_exc}")

            rel = new_path.replace("\\", "/")
            idx = rel.find("assets/")
            img_url = f"/{rel[idx:]}" if idx >= 0 else None
            print(f"[이미지 재생성] 컷 {req.cutIndex + 1} {model_name}으로 재생성 완료")
            return {"ok": True, "image_url": img_url, "model": model_name}
        else:
            return JSONResponse(status_code=500, content={"error": "이미지 생성 실패"})

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"재생성 실패: {str(e)}"})


# ── POST /api/register-day-session ───────────────────────────────


@router.post("/register-day-session")
async def register_day_session(req: RegisterDaySessionRequest):
    """Day 파일 스크립트를 백엔드 세션으로 등록 (이미지 생성용)."""
    folder_name = f"{req.topic.replace(' ', '_')}_{req.channel}"
    topic_folder = folder_name
    full_path = os.path.join("assets", folder_name)
    os.makedirs(os.path.join(full_path, "images"), exist_ok=True)

    # cuts 정규화
    normalized_cuts = []
    for c in req.cuts:
        normalized_cuts.append({
            "script": c.get("script", ""),
            "prompt": c.get("prompt", c.get("image_prompt", "")),
            "description": c.get("description", ""),
        })

    # cuts.json 저장
    cuts_path = os.path.join(full_path, "cuts.json")
    with open(cuts_path, "w", encoding="utf-8") as f:
        json.dump({
            "cuts": normalized_cuts,
            "title": req.topic,
            "tags": [],
            "metadata": {
                "topic": req.topic,
                "channel": req.channel,
                "source": "day_file",
            }
        }, f, ensure_ascii=False, indent=2)

    # 이미 생성된 이미지 파일 자동 탐지
    image_paths = []
    alt_path = os.path.join("assets", full_path)
    for i in range(len(normalized_cuts)):
        img_file = os.path.join(full_path, "images", f"cut_{i:02}.png")
        alt_file = os.path.join(alt_path, "images", f"cut_{i:02}.png")
        if os.path.exists(img_file):
            image_paths.append(img_file)
        elif os.path.exists(alt_file):
            image_paths.append(alt_file)
        else:
            image_paths.append("")

    # 언어 매핑
    lang_map = {"askanything": "ko", "wonderdrop": "en", "exploratodo": "es", "prismtale": "es"}

    with session_lock:
        prepared_sessions[req.sessionId] = {
            "topic": req.topic,
            "title": req.topic,
            "topic_folder": topic_folder,
            "channel": req.channel,
            "language": lang_map.get(req.channel, "ko"),
            "cuts": normalized_cuts,
            "image_paths": image_paths,
            "_created": __import__('time').time(),
        }

    existing_count = sum(1 for p in image_paths if p)
    image_urls = []
    for p in image_paths:
        if p:
            rel = p.replace("\\", "/")
            idx = rel.find("assets/")
            image_urls.append(f"/{rel[idx:]}" if idx >= 0 else None)
        else:
            image_urls.append(None)
    print(f"[Day 세션] {req.channel}: {existing_count}/{len(normalized_cuts)} 이미지 발견 (folder={folder_name})")
    return {"ok": True, "sessionId": req.sessionId, "cuts_count": len(normalized_cuts), "existing_images": existing_count, "image_urls": image_urls}


# ── POST /api/batch-generate-images ──────────────────────────────


@router.post("/batch-generate-images")
async def batch_generate_images(req: BatchImageRequest):
    """세션의 모든 컷 이미지를 일괄 생성합니다."""
    with session_lock:
        session = prepared_sessions.get(req.sessionId)
    if not session:
        return JSONResponse(status_code=404, content={"error": "세션을 찾을 수 없습니다."})

    cuts = session.get("cuts", [])
    topic_folder = session.get("topic_folder", "default_topic")
    topic = session.get("topic", "")
    gemini_keys = os.getenv("GEMINI_API_KEYS", os.getenv("GEMINI_API_KEY", ""))

    results = []
    model_name = req.model or "standard"
    model_map = {
        "standard": "imagen-4.0-generate-001",
        "fast": "imagen-4.0-fast-generate-001",
        "ultra": "imagen-4.0-ultra-generate-001",
    }

    for i, cut in enumerate(cuts):
        prompt = cut.get("prompt", cut.get("image_prompt", ""))
        if not prompt:
            results.append({"index": i, "ok": False, "error": "프롬프트 없음"})
            continue
        try:
            new_path = None
            if model_name in ("standard", "fast", "ultra"):
                from modules.image.imagen import generate_image_imagen
                new_path = generate_image_imagen(
                    prompt, i, topic_folder,
                    model_override=model_map[model_name],
                    gemini_api_keys=gemini_keys, topic=topic,
                )
            elif model_name == "nano_banana":
                from modules.image.imagen import generate_image_nano_banana
                new_path = generate_image_nano_banana(
                    prompt, i, topic_folder,
                    gemini_api_keys=gemini_keys, topic=topic,
                )
            elif model_name == "dalle":
                from modules.image.dalle import generate_image as generate_image_dalle
                new_path = generate_image_dalle(prompt, i, topic_folder, topic=topic)

            if new_path and os.path.exists(new_path):
                cost_channel = "unknown"
                with session_lock:
                    if req.sessionId in prepared_sessions:
                        if "image_paths" not in prepared_sessions[req.sessionId]:
                            prepared_sessions[req.sessionId]["image_paths"] = [""] * len(cuts)
                        prepared_sessions[req.sessionId]["image_paths"][i] = new_path
                        cost_channel = prepared_sessions[req.sessionId].get("channel") or cost_channel
                try:
                    from modules.utils.cost_tracker import record_asset_cost
                    record_asset_cost(channel=cost_channel, image_count=1)
                except Exception as cost_exc:
                    print(f"[비용 추적] 일괄 이미지 비용 기록 실패(무시): {cost_exc}")
                rel = new_path.replace("\\", "/")
                idx = rel.find("assets/")
                img_url = f"/{rel[idx:]}" if idx >= 0 else None
                results.append({"index": i, "ok": True, "image_url": img_url})
                print(f"[일괄 이미지] 컷 {i+1}/{len(cuts)} 생성 완료")
            else:
                results.append({"index": i, "ok": False, "error": "생성 실패"})
        except Exception as e:
            results.append({"index": i, "ok": False, "error": str(e)})

    success_count = sum(1 for r in results if r.get("ok"))
    return {
        "ok": True,
        "total": len(cuts),
        "success": success_count,
        "failed": len(cuts) - success_count,
        "results": results,
    }


# ── POST /api/render (SSE) ───────────────────────────────────────


@router.post("/render")
async def render_endpoint(req: RenderRequest):
    """2단계: 수정된 스크립트로 TTS → Whisper → Remotion 렌더링."""
    _cleanup_sessions()
    with session_lock:
        session = prepared_sessions.get(req.sessionId)
    if not session:
        return JSONResponse(status_code=404, content={"error": "세션이 만료되었습니다. 다시 준비해주세요."})

    async def sse_generator():
        # lazy imports
        from modules.tts.elevenlabs import generate_tts, prepare_spoken_script
        from modules.utils.audio import normalize_audio_lufs
        from modules.transcription.whisper import generate_word_timestamps
        from modules.video.remotion import create_remotion_video
        from modules.video.engines import generate_video_from_image
        from modules.utils.keys import get_google_key
        from modules.utils.channel_config import get_channel_preset

        def _extract_emotion_tag(description: str) -> str | None:
            match = re.search(r"\[(SHOCK|WONDER|TENSION|REVEAL|URGENCY|DISBELIEF|IDENTITY|CALM|LOOP)\]", description or "", re.IGNORECASE)
            return match.group(1).upper() if match else None

        def _pick_hero_indices(cuts_data: list[dict]) -> list[int]:
            priority_groups = [
                {"SHOCK", "REVEAL"},
                {"URGENCY", "DISBELIEF", "TENSION"},
                {"WONDER", "IDENTITY", "LOOP", "CALM"},
            ]
            hero_indices: list[int] = []
            seen: set[int] = set()
            emotions = [_extract_emotion_tag(cut.get("description", "")) for cut in cuts_data]

            for group in priority_groups:
                for idx, emotion in enumerate(emotions):
                    if emotion in group and idx not in seen:
                        hero_indices.append(idx)
                        seen.add(idx)
                if hero_indices:
                    break

            if not hero_indices and cuts_data:
                hero_indices = [0]
            return hero_indices

        try:
            cuts = copy.deepcopy(session["cuts"])
            topic_folder = session["topic_folder"]
            video_title = session["title"]
            image_paths = session["image_paths"]
            language = session["language"]
            api_key_override = req.apiKey or os.getenv("OPENAI_API_KEY", "")
            elevenlabs_key_override = req.elevenlabsKey or os.getenv("ELEVENLABS_API_KEY", "")

            # 채널 프리셋 fallback: cameraStyle은 사용자가 명시 선택한 값을 유지.
            if req.channel:
                _ch_preset = get_channel_preset(req.channel)

            # 수정된 스크립트 반영
            script_updates = {c["index"]: c["script"] for c in req.cuts if "script" in c}
            for idx, new_script in script_updates.items():
                if 0 <= idx < len(cuts):
                    cuts[idx]["script"] = prepare_spoken_script(new_script, language)

            for cut in cuts:
                cut["script"] = prepare_spoken_script(cut.get("script", ""), language)

            scripts = [cut["script"] for cut in cuts]
            loop = asyncio.get_running_loop()

            # 음성 선택: voiceId(auto/직접) > 채널 설정 > 기본값
            render_voice_id = None
            render_voice_settings = None
            if req.voiceId == "auto":
                render_voice_id = _auto_select_voice(video_title, language)
            elif req.voiceId:
                render_voice_id = req.voiceId
            if not render_voice_id:
                render_preset = get_channel_preset(req.channel)
                if render_preset:
                    render_voice_id = render_preset.get("voice_id")
                    render_voice_settings = render_preset.get("voice_settings")
            else:
                _rp = get_channel_preset(req.channel)
                if _rp:
                    render_voice_settings = _rp.get("voice_settings")

            yield {"data": "PROG|10\n"}
            yield {"data": "[음성] TTS 녹음 + 타임스탬프 추출 시작...\n"}

            # TTS + Whisper (순차)
            audio_paths = []
            word_timestamps_list = []
            for i, script in enumerate(scripts):
                try:
                    aud = await loop.run_in_executor(
                        None, lambda idx=i, s=script: generate_tts(s, idx, topic_folder, elevenlabs_key_override, language=language, speed=req.ttsSpeed, voice_id=render_voice_id, voice_settings=render_voice_settings, already_prepared=True)
                    )
                    if aud:
                        aud = normalize_audio_lufs(aud)
                    audio_paths.append(aud)
                except Exception as exc:
                    print(f"[컷 {i+1} TTS 실패] {exc}")
                    audio_paths.append(None)

                # Whisper 타임스탬프
                words = []
                if audio_paths[-1]:
                    try:
                        words = await loop.run_in_executor(
                            None, lambda a=audio_paths[-1]: generate_word_timestamps(a, api_key_override, language=language)
                        )
                    except Exception as exc:
                        print(f"[컷 {i+1} Whisper 실패] {exc}")
                word_timestamps_list.append(words or [])

                prog = 10 + int(50 * ((i + 1) / len(scripts)))
                yield {"data": f"PROG|{prog}\n"}
                yield {"data": f"  -> 컷 {i+1}/{len(scripts)} 음성 완료\n"}

            # 비디오 변환 (선택) — 히어로 컷(SHOCK/REVEAL)만 비디오 생성
            visual_paths = list(image_paths)
            generated_video_count = 0
            active_video_engine = req.videoEngine
            if active_video_engine != "none":
                hero_only = req.videoModel == "hero-only"
                actual_veo_model = req.videoModel if req.videoModel and req.videoModel != "hero-only" else None
                target_indices = _pick_hero_indices(cuts) if hero_only else list(range(len(cuts)))
                skip_count = len(cuts) - len(target_indices)
                if hero_only and skip_count > 0:
                    hero_labels = [f"{idx + 1}컷" for idx in target_indices]
                    yield {"data": f"[비디오] hero-only 모드 — Veo3 대상: {', '.join(hero_labels)} (나머지 {skip_count}개는 Ken Burns)\n"}
                elif not hero_only:
                    yield {"data": f"[비디오] {active_video_engine} 전체 컷 변환 중... ({len(target_indices)}개 컷)\n"}

                for i, img_path in enumerate(image_paths):
                    if img_path and os.path.exists(img_path) and i in target_indices:
                        try:
                            llm_key = req.llmKey
                            vid_key = get_google_key(llm_key, service=active_video_engine, extra_keys=req.geminiKeys)
                            vid = await loop.run_in_executor(
                                None,
                                lambda idx=i, ip=img_path, p=cuts[idx]["prompt"], vk=vid_key, desc=cuts[idx].get("description", ""):
                                    generate_video_from_image(
                                        ip,
                                        p,
                                        idx,
                                        topic_folder,
                                        active_video_engine,
                                        vk,
                                        description=desc,
                                        veo_model=actual_veo_model,
                                        gemini_api_keys=req.geminiKeys,
                                    ),
                            )
                            if vid:
                                visual_paths[i] = vid
                                generated_video_count += 1
                                yield {"data": f"  -> 컷 {i+1}/{len(cuts)} Veo 영상 생성 완료\n"}
                            else:
                                yield {"data": f"WARN|  -> 컷 {i+1}/{len(cuts)} Veo 생성 실패, 정지 이미지 유지\n"}
                        except Exception as exc:
                            print(f"[컷 {i+1} 비디오 변환 실패] {exc}")
                            yield {"data": f"WARN|  -> 컷 {i+1}/{len(cuts)} 비디오 변환 예외, 정지 이미지 유지\n"}

            # 실패 체크
            failed = [i+1 for i, p in enumerate(audio_paths) if p is None]
            if failed:
                yield {"data": f"ERROR|[TTS 오류] 컷 {failed} 음성 생성 실패\n"}
                return

            try:
                from modules.utils.cost_tracker import record_asset_cost

                record_asset_cost(
                    channel=req.channel or session.get("channel") or "unknown",
                    video_count=generated_video_count,
                    tts_chars=sum(len(s or "") for s in scripts),
                )
            except Exception as cost_exc:
                print(f"[비용 추적] 렌더 비용 기록 실패(무시): {cost_exc}")

            yield {"data": "PROG|70\n"}
            yield {"data": "[렌더링] Remotion 렌더링 시작...\n"}

            # Remotion 렌더. 로컬 브라우저/파일 로딩 타임아웃은 비용 재발생 없이 재시도 가능.
            render_result = None
            for render_attempt in range(1, 3):
                if render_attempt > 1:
                    yield {"data": f"WARN|[Remotion 재시도] 로컬 렌더를 다시 시도합니다 ({render_attempt}/2)\n"}
                    await asyncio.sleep(5)
                render_result = await loop.run_in_executor(
                    None,
                    lambda: create_remotion_video(
                        visual_paths, audio_paths, scripts,
                        word_timestamps_list, topic_folder, title=video_title,
                        camera_style=req.cameraStyle, bgm_theme=req.bgmTheme,
                        channel=req.channel, platforms=req.platforms,
                        caption_size=req.captionSize,
                        caption_y=req.captionY,
                        descriptions=[cut.get("description", "") for cut in cuts],
                    ),
                )
                if render_result:
                    if render_attempt > 1:
                        yield {"data": "[Remotion 재시도] 성공\n"}
                    break

            if not render_result:
                import traceback as _tb
                print("[Remotion 오류] render_result가 None — 상세 로그는 위 터미널 출력을 확인하세요.")
                yield {"data": "ERROR|[Remotion 오류] 렌더링 실패 — 터미널에서 상세 로그를 확인하세요.\n"}
                return

            # 결과 처리
            if isinstance(render_result, str):
                video_paths_map = {"youtube": render_result}
            else:
                video_paths_map = render_result

            primary_path = next(iter(video_paths_map.values()))

            # Downloads 복사
            downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            for plat, vpath in video_paths_map.items():
                fname = os.path.basename(vpath)
                if os.path.isdir(downloads_dir):
                    try:
                        await asyncio.to_thread(shutil.copy2, os.path.abspath(vpath), os.path.join(downloads_dir, fname))
                        if len(video_paths_map) > 1:
                            yield {"data": f"[저장] {plat.upper()} → Downloads/{fname}\n"}
                    except Exception as cp_err:
                        print(f"[Downloads 복사 실패] {cp_err}")

            yield {"data": "PROG|100\n"}
            final_filename = os.path.basename(primary_path)
            relative_video_path = f"/assets/{topic_folder}/video/{final_filename}"
            platform_count = len(video_paths_map)
            if platform_count > 1:
                yield {"data": f"[완료] {platform_count}개 플랫폼 영상 렌더링 대성공!\n"}
            else:
                yield {"data": f"[완료] 영상 렌더링 대성공! 📂 Downloads 폴더에 저장됨\n"}
            yield {"data": f"DONE|{relative_video_path}|\n"}

        except Exception as e:
            traceback.print_exc()
            safe_msg = re.sub(r"(AIza|sk-|key=|token=|Bearer )[A-Za-z0-9_\-]{4,}", r"\1***", str(e)[:200])
            yield {"data": f"ERROR|[렌더 오류] {safe_msg}\n"}
        finally:
            # 성공/실패 관계없이 세션 정리 (메모리 누수 방지)
            with session_lock:
                prepared_sessions.pop(req.sessionId, None)

    return EventSourceResponse(sse_generator())


# ── GET /api/sessions ────────────────────────────────────────────


@router.get("/sessions")
async def list_sessions():
    """assets/ 폴더에서 이미지가 있는 세션 목록 반환."""
    sessions = []
    for folder_path in glob.glob("assets/*/images"):
        folder = os.path.dirname(folder_path)
        folder_name = os.path.basename(folder)
        if folder_name in (".cache", "assets"):
            continue
        try:
            img_count = len(glob.glob(os.path.join(folder_path, "cut_*.png")))
            if img_count == 0:
                continue
            vid_dir = os.path.join(folder, "video")
            has_video = bool(glob.glob(os.path.join(vid_dir, "*.mp4"))) if os.path.isdir(vid_dir) else False
            has_audio = bool(glob.glob(os.path.join(folder, "audio", "cut_*.mp3"))) if os.path.isdir(os.path.join(folder, "audio")) else False
            # cuts.json이 있으면 메타데이터 로드
            cuts_path = os.path.join(folder, "cuts.json")
            title = folder_name
            cuts_count = img_count
            channel = folder_name.rsplit("_", 1)[-1] if "_" in folder_name else ""
            language = ""
            created_at = ""
            has_cuts = os.path.exists(cuts_path) and os.path.getsize(cuts_path) > 2
            if has_cuts:
                with open(cuts_path, encoding="utf-8") as f:
                    data = json.load(f)
                title = data.get("title", folder_name)
                cuts_count = len(data.get("cuts", []))
                meta = data.get("metadata", {})
                channel = meta.get("channel", channel)
                language = meta.get("language", "")
                created_at = meta.get("created_at", "")
            # 생성 시간 없으면 폴더 수정 시간 사용
            if not created_at:
                mtime = os.path.getmtime(folder_path)
                from datetime import datetime
                created_at = datetime.fromtimestamp(mtime).isoformat()
            sessions.append({
                "folder": folder_name,
                "title": title,
                "cuts_count": cuts_count,
                "image_count": img_count,
                "has_video": has_video,
                "has_audio": has_audio,
                "has_cuts": has_cuts,
                "channel": channel,
                "language": language,
                "created_at": created_at,
            })
        except Exception:
            continue
    sessions.sort(key=lambda s: s.get("created_at", ""), reverse=True)
    return {"sessions": sessions}


# ── POST /api/sessions/load ──────────────────────────────────────


@router.post("/sessions/load")
async def load_session(req: LoadSessionRequest):
    """저장된 세션을 메모리에 복원하고 sessionId 반환."""
    folder_name = os.path.basename(req.folder)  # path traversal 방지
    topic_folder = os.path.join("assets", folder_name)
    cuts_path = os.path.join(topic_folder, "cuts.json")

    # 이미지 파일 목록
    img_dir = os.path.join(topic_folder, "images")
    if not os.path.isdir(img_dir):
        raise HTTPException(status_code=404, detail="이미지 폴더가 없습니다")
    img_files = sorted(glob.glob(os.path.join(img_dir, "cut_*.png")))
    if not img_files:
        raise HTTPException(status_code=404, detail="이미지가 없습니다")

    # cuts.json이 있으면 메타데이터 로드, 없으면 이미지 기반 생성
    if os.path.exists(cuts_path) and os.path.getsize(cuts_path) > 2:
        with open(cuts_path, encoding="utf-8") as f:
            data = json.load(f)
        cuts = data.get("cuts", [])
        title = data.get("title", folder_name)
        tags = data.get("tags", [])
        meta = data.get("metadata", {})
    else:
        # cuts.json 없으면 빈 스크립트로 즉시 로드
        topic_guess = folder_name.rsplit("_", 1)[0].replace("_", " ") if "_" in folder_name else folder_name
        channel_guess = folder_name.rsplit("_", 1)[-1] if "_" in folder_name else ""
        lang_map = {"askanything": "ko", "wonderdrop": "en", "exploratodo": "es", "prismtale": "es"}
        lang = lang_map.get(channel_guess, "ko")
        cuts = [{"script": "", "prompt": "", "description": "", "index": i} for i, _ in enumerate(img_files)]
        title = topic_guess
        tags = []
        meta = {"topic": topic_guess, "channel": channel_guess, "language": lang}

    image_paths = list(img_files)

    # 이미지 수와 스크립트 수 맞추기
    n = min(len(image_paths), len(cuts))
    image_paths = image_paths[:n]
    cuts = cuts[:n]

    # 세션 등록
    import uuid, time as _time
    session_id = uuid.uuid4().hex[:16]
    _cleanup_sessions()
    with session_lock:
        prepared_sessions[session_id] = {
            "sessionId": session_id,
            "cuts": cuts,
            "topic_folder": folder_name,
            "title": title,
            "tags": tags,
            "image_paths": image_paths,
            "topic": meta.get("topic", title),
            "channel": meta.get("channel", ""),
            "language": meta.get("language", "ko"),
            "_created": _time.time(),
        }

    # 프론트엔드용 응답
    preview_cuts = []
    for i, cut in enumerate(cuts):
        img_url = f"/assets/{folder_name}/images/cut_{i:02d}.png" if image_paths[i] else None
        preview_cuts.append({
            "index": i,
            "script": cut.get("script", cut.get("text", "")),
            "prompt": cut.get("prompt", ""),
            "description": cut.get("description", ""),
            "image_url": img_url,
        })

    # 기존 Veo3 영상 자동 감지 → 비디오 엔진 추천
    video_clips_dir = os.path.join("assets", folder_name, "video_clips")
    existing_videos = 0
    if os.path.isdir(video_clips_dir):
        existing_videos = len([f for f in os.listdir(video_clips_dir)
                              if f.endswith(".mp4") and os.path.getsize(os.path.join(video_clips_dir, f)) > 10000])

    if existing_videos == 0:
        recommended_engine = "none"        # 이미지만 → Ken Burns
        recommended_model = ""
    elif existing_videos >= len(cuts):
        recommended_engine = "veo3"        # 전체 영상 있음 → Standard
        recommended_model = ""
    else:
        recommended_engine = "veo3"        # 일부만 있음 → Hero Only
        recommended_model = "hero-only"

    return {
        "sessionId": session_id,
        "title": title,
        "cuts": preview_cuts,
        "channel": meta.get("channel", ""),
        "tags": tags,
        "recommendedVideoEngine": recommended_engine,
        "recommendedVideoModel": recommended_model,
        "existingVideos": existing_videos,
    }


# ── POST /api/sessions/generate-scripts ──────────────────────────


@router.post("/sessions/generate-scripts")
async def generate_scripts(req: GenerateScriptsRequest):
    """세션의 이미지에 맞는 스크립트를 LLM으로 생성합니다."""
    folder_path = os.path.join("assets", req.folder)
    if not os.path.isdir(folder_path):
        return {"error": "폴더를 찾을 수 없습니다"}

    topic = req.topic
    if not topic:
        name = req.folder
        for suffix in ("_askanything", "_wonderdrop", "_exploratodo", "_prismtale"):
            if name.endswith(suffix):
                name = name[: -len(suffix)]
                break
        topic = name.replace("_", " ")

    try:
        from modules.gpt.cutter import generate_cuts
        cuts_list, _folder, title, tags, _desc, _fact_ctx = generate_cuts(topic, lang=req.lang, channel=req.channel, llm_provider="gemini")

        # 이미지 수에 맞춤
        img_count = len(glob.glob(os.path.join(folder_path, "images", "cut_*.png")))
        if img_count > 0:
            cuts_list = cuts_list[:img_count]

        # cuts.json 저장
        cuts_path = os.path.join(folder_path, "cuts.json")
        from datetime import datetime
        with open(cuts_path, "w", encoding="utf-8") as f:
            json.dump({
                "cuts": cuts_list, "title": title, "tags": tags,
                "metadata": {"topic": topic, "channel": req.channel, "language": req.lang,
                             "created_at": datetime.now().isoformat()}
            }, f, ensure_ascii=False, indent=2)

        # 프론트엔드용 응답
        result_cuts = []
        for i, cut in enumerate(cuts_list):
            result_cuts.append({
                "index": i,
                "script": cut.get("script", cut.get("text", "")),
                "prompt": cut.get("prompt", ""),
                "description": cut.get("description", ""),
            })

        return {"title": title, "cuts": result_cuts, "tags": tags}
    except Exception as e:
        return {"error": f"스크립트 생성 실패: {str(e)}"}
