"""생성 라우터 — v1 SSE 스트리밍 + v2 오케스트라 파이프라인.

api_server.py에서 추출한 /api/generate, /api/generate/v2,
/api/analyze-shorts, /api/cancel, /api/status, / 엔드포인트.
"""

import os
import re
import asyncio
import threading
import json
import shutil
import traceback
import copy

from pydantic import BaseModel, Field, field_validator
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from routes.shared import (
    generate_semaphore,
    cancel_events,
    active_generation_ids,
    generation_lock,
    CANCEL_EVENT_TTL,
    cut_executor,
    image_semaphore,
    resolve_youtube_topic,
    VOICE_MAP,
    VOICE_ID_TO_NAME,
)
from modules.utils.hero_cuts import pick_hero_indices
from modules.utils.provider_policy import get_openai_api_key, is_openai_api_disabled

router = APIRouter(tags=["generate"])


# ── 음성 선택 + 키 검증 → services/ ──────────────────────────────
from services.voice import auto_select_voice as _auto_select_voice, voice_name as _voice_name
from services.keys import validate_keys as _validate_keys


# ── Pydantic 모델 ────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    apiKey: str | None = None
    elevenlabsKey: str | None = None
    videoEngine: str = "veo3"
    imageEngine: str = "imagen"
    llmProvider: str = "gemini"
    llmModel: str | None = None    # 세부 모델 버전 (예: "gemini-2.0-flash", "gpt-4o-mini")
    imageModel: str | None = None  # 이미지 모델 버전 (예: "imagen-4.0-fast-generate-001")
    videoModel: str | None = None  # 비디오 모델 버전 (예: "veo-3.0-fast-generate-001")
    llmKey: str | None = None
    geminiKeys: str | None = None  # 프론트엔드 멀티키 (쉼표 구분)
    outputPath: str | None = None
    language: str = "ko"
    cameraStyle: str = "auto"
    bgmTheme: str = "random"
    formatType: str | None = None  # 포맷 타입: WHO_WINS, IF, EMOTIONAL_SCI, FACT, COUNTDOWN, SCALE, PARADOX, MYSTERY
    channel: str | None = None  # 채널별 인트로/아웃트로: "askanything", "wonderdrop" 등
    platforms: list[str] = ["youtube"]  # 렌더 플랫폼: "youtube", "tiktok", "reels"
    ttsSpeed: float = 1.05  # TTS 속도: 0.7(느림) ~ 1.05(기본) ~ 1.3(빠름)
    voiceId: str | None = None  # ElevenLabs 음성 ID
    captionSize: int = Field(48, ge=32, le=72)  # 자막 폰트 크기 (px)
    captionY: int = Field(28, ge=10, le=50)  # 자막 높이 (%): 하단 기준
    referenceUrl: str | None = None  # YouTube 레퍼런스 URL (분석 후 스타일 반영)
    publishMode: str = "local"  # local(업로드 안 함) / realtime(공개) / private(비공개) / scheduled(예약)
    scheduledTime: str | None = None  # ISO datetime (예약 모드 전용)
    workflowMode: str = "fast"  # fast(즉시 렌더) / review(초안만 생성, 검수 후 렌더)
    maxCuts: int | None = None  # 테스트 모드: 컷 수 제한 (예: 3)
    seriesTitle: str | None = None  # 시리즈 재생목록 제목 (배치 전용)

    @field_validator("workflowMode")
    @classmethod
    def valid_workflow_mode(cls, v: str) -> str:
        allowed = {"fast", "review"}
        if v not in allowed:
            raise ValueError(f"지원하지 않는 workflowMode: {v}. 허용: {allowed}")
        return v

    @field_validator("language")
    @classmethod
    def valid_language(cls, v: str) -> str:
        allowed = {"ko", "en", "de", "da", "no", "es", "fr", "pt", "it", "nl", "sv", "pl", "ru", "ja", "zh", "ar", "tr", "hi", "auto"}
        if v not in allowed:
            raise ValueError(f"지원하지 않는 언어: {v}. 허용: {allowed}")
        return v

    @field_validator("topic")
    @classmethod
    def topic_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("주제(topic)가 비어 있습니다.")
        return v.strip()

    @field_validator("videoEngine")
    @classmethod
    def valid_engine(cls, v: str) -> str:
        allowed = {"kling", "sora2", "veo3", "blender", "none"}
        if v not in allowed:
            raise ValueError(f"지원하지 않는 비디오 엔진: {v}. 허용: {allowed}")
        if v == "sora2" and is_openai_api_disabled():
            raise ValueError("OpenAI API 비활성화 상태에서는 Sora 2를 사용할 수 없습니다.")
        return v

    @field_validator("imageEngine")
    @classmethod
    def valid_image_engine(cls, v: str) -> str:
        allowed = {"dalle", "imagen", "nano_banana"}
        if v not in allowed:
            raise ValueError(f"지원하지 않는 이미지 엔진: {v}. 허용: {allowed}")
        if v == "dalle" and is_openai_api_disabled():
            raise ValueError("OpenAI API 비활성화 상태에서는 DALL-E를 사용할 수 없습니다.")
        return v

    @field_validator("llmProvider")
    @classmethod
    def valid_llm_provider(cls, v: str) -> str:
        allowed = {"openai", "gemini", "claude"}
        if v not in allowed:
            raise ValueError(f"지원하지 않는 LLM 프로바이더: {v}. 허용: {allowed}")
        if v == "openai" and is_openai_api_disabled():
            raise ValueError("OpenAI API 비활성화 상태에서는 GPT 기획을 사용할 수 없습니다.")
        return v


class AnalyzeShortsRequest(BaseModel):
    url: str = Field(..., min_length=5)


# ── 엔드포인트 ────────────────────────────────────────────────────

@router.get("/")
async def root():
    return {
        "status": "running",
        "name": "AskAnything Video Generator API",
        "endpoints": {
            "POST /api/generate": "비디오 생성 (SSE 스트리밍)",
            "GET /api/engines": "사용 가능한 비디오 엔진 목록",
        },
    }


@router.post("/api/analyze-shorts")
async def analyze_shorts(req: AnalyzeShortsRequest):
    """YouTube URL을 분석하여 메타데이터 + 자막 + 구조를 반환합니다."""
    from modules.utils.youtube_extractor import extract_youtube_reference
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, lambda: extract_youtube_reference(req.url))
    if not result:
        return JSONResponse(status_code=400, content={"error": "유효한 YouTube URL이 아니거나 분석에 실패했습니다."})
    return {
        "video_id": result.get("video_id", ""),
        "title": result.get("title", ""),
        "channel": result.get("channel", ""),
        "view_count": result.get("view_count", 0),
        "like_count": result.get("like_count", 0),
        "transcript": result.get("transcript", "")[:1000],  # 프리뷰용 1000자 제한
        "structure": result.get("structure", {}),
    }


@router.post("/api/cancel")
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


@router.get("/api/status")
async def generation_status():
    """현재 생성 상태 확인."""
    with generation_lock:
        return {
            "active": len(active_generation_ids) > 0,
            "generation_ids": list(active_generation_ids),
            "count": len(active_generation_ids),
        }


# ── v1 SSE 스트리밍 파이프라인 ────────────────────────────────────

@router.post("/api/generate")
async def generate_video_endpoint(req: GenerateRequest):
    # lazy imports
    from modules.gpt.cutter import generate_cuts
    from modules.image.dalle import generate_image as generate_image_dalle
    from modules.image.imagen import generate_image_imagen, generate_image_nano_banana
    from modules.video.engines import generate_video_from_image, check_engine_available
    from modules.tts.elevenlabs import generate_tts, prepare_spoken_script, check_quota as check_elevenlabs_quota
    from modules.transcription.whisper import generate_word_timestamps
    from modules.video.remotion import create_remotion_video
    from modules.utils.constants import PROVIDER_LABELS
    from modules.utils.keys import get_google_key, count_google_keys, count_available_keys
    from modules.utils.audio import normalize_audio_lufs
    from modules.utils.channel_config import get_channel_preset

    topic = req.topic
    api_key_override = get_openai_api_key(req.apiKey)
    elevenlabs_key_override = req.elevenlabsKey
    video_engine = req.videoEngine
    image_engine = req.imageEngine
    llm_provider = req.llmProvider
    llm_key_override = req.llmKey
    output_path = req.outputPath
    language = req.language

    import uuid as _uuid
    generation_id = _uuid.uuid4().hex[:8]

    # 모델 버전 오버라이드: 함수 파라미터로 직접 전달 (os.environ 비사용)
    llm_model_override = req.llmModel or None
    image_model_override = req.imageModel or None
    video_model_override = req.videoModel or None
    gemini_keys_override = req.geminiKeys or None

    async def sse_generator():
        # A/B 변형 + 메타데이터 안전 초기화
        cut1_ab_variants: list = []
        video_desc = ""
        video_tags: list = []
        cost_recorded = False
        generation_completed = False
        generation_cancelled = False

        def _record_generation_cost_once(
            *,
            success: bool,
            llm_usd: float = 0.0,
            image_count: int = 0,
            video_count: int = 0,
            video_model: str | None = None,
            tts_chars: int = 0,
        ) -> None:
            nonlocal cost_recorded
            if cost_recorded:
                return
            try:
                from modules.utils.cost_tracker import record_generation_cost
                record_generation_cost(
                    channel=req.channel or "unknown",
                    success=success,
                    llm_usd=llm_usd,
                    image_count=image_count,
                    video_count=video_count,
                    video_model=video_model,
                    tts_chars=tts_chars,
                )
            except Exception:
                pass  # 비용 기록 실패가 파이프라인을 중단하면 안 됨
            finally:
                cost_recorded = True

        # 새 작업 등록 (요청별 이벤트로 격리, 자동 취소 없음)
        import time as _t
        cancel_event = threading.Event()
        with generation_lock:
            # 오래된 이벤트 정리 (메모리 누수 방지)
            now = _t.time()
            stale = [gid for gid, (_, ts) in cancel_events.items() if now - ts > CANCEL_EVENT_TTL]
            for gid in stale:
                cancel_events.pop(gid, None)
                active_generation_ids.discard(gid)
            cancel_events[generation_id] = (cancel_event, now)
            active_generation_ids.add(generation_id)

        def _is_cancelled() -> bool:
            return cancel_event.is_set()

        # 동시 요청 제한: 슬롯 부족 시 대기 안내
        # 프론트엔드에 generation_id 전달 (멀티채널 취소용)
        yield {"data": f"GEN_ID|{generation_id}\n"}

        if generate_semaphore.locked():
            yield {"data": "WARN|[대기열] 다른 비디오가 생성 중입니다. 순서를 기다리는 중...\n"}
        async with generate_semaphore:
          try:
            # 사전 검증: 필수 API 키 확인
            missing = _validate_keys(api_key_override, elevenlabs_key_override, video_engine, image_engine, llm_provider, llm_key_override)
            if missing:
                yield {"data": "ERROR|[환경 설정 오류] 다음 API 키가 누락되었거나 유효하지 않습니다:\n"}
                for m in missing:
                    yield {"data": f"ERROR|  - {m}\n"}
                yield {"data": "ERROR|.env 파일을 확인하거나, 프론트엔드에서 API Key를 입력해주세요.\n"}
                return

            # 사전 검증: API 쿼터 체크 (경고만, 차단 안 함) — Qwen3 TTS 시 스킵
            el_key = elevenlabs_key_override or os.getenv("ELEVENLABS_API_KEY", "")
            quota_info = check_elevenlabs_quota(el_key) if os.getenv("TTS_ENGINE", "qwen3").lower() != "qwen3" else None
            if quota_info:
                remaining = quota_info["remaining"]
                limit = quota_info["limit"]
                pct = (remaining / limit * 100) if limit > 0 else 0
                if remaining < 500:
                    yield {"data": f"WARN|[ElevenLabs 잔여 크레딧 부족] {remaining:,}/{limit:,}자 남음 ({pct:.0f}%). 생성이 중단될 수 있습니다.\n"}
                elif pct < 20:
                    yield {"data": f"WARN|[ElevenLabs 크레딧 경고] {remaining:,}/{limit:,}자 남음 ({pct:.0f}%).\n"}

            # Google 키 가용성 경고
            if os.getenv("GEMINI_BACKEND") != "vertex_ai":
                total_keys = count_google_keys(extra_keys=gemini_keys_override)
                avail_keys = count_available_keys(extra_keys=gemini_keys_override)
                if total_keys > 0 and avail_keys < total_keys:
                    blocked_count = total_keys - avail_keys
                    if avail_keys == 0:
                        yield {"data": f"WARN|[Google 키 경고] 모든 {total_keys}개 키가 429 차단됨. 쿼터 초과 가능성 높음.\n"}
                    else:
                        yield {"data": f"WARN|[Google 키 상태] {avail_keys}/{total_keys}개 사용 가능 ({blocked_count}개 24시간 차단 중)\n"}

            provider_label = PROVIDER_LABELS.get(llm_provider, "ChatGPT")

            # 채널 프리셋 fallback: 속도/자막 기본값만 보정.
            # cameraStyle은 사용자가 cinematic/auto 등을 명시 선택할 수 있으므로 덮어쓰지 않는다.
            if req.channel:
                _ch_preset = get_channel_preset(req.channel)
                if _ch_preset:
                    if _ch_preset.get("tts_speed") is not None:
                        req.ttsSpeed = _ch_preset["tts_speed"]
                    if _ch_preset.get("caption_size"):
                        req.captionSize = _ch_preset["caption_size"]
                    if _ch_preset.get("caption_y"):
                        req.captionY = _ch_preset["caption_y"]

            # 비디오 엔진 변수 초기화 (아래에서 키 선택·사전 검증에 사용)
            active_video_engine = video_engine

            # Google 키 로테이션 (비디오 엔진용 — 서비스별 차단 고려)
            video_svc = active_video_engine if active_video_engine in ("veo3",) else None
            google_key_for_video = get_google_key(llm_key_override, service=video_svc, extra_keys=gemini_keys_override)

            # 비디오 엔진 사전 검증
            if active_video_engine != "none":
                engine_ok, engine_reason = check_engine_available(active_video_engine, google_key_for_video)
                if not engine_ok:
                    yield {"data": f"WARN|[비디오 엔진 경고] {active_video_engine}: {engine_reason}. 정지 이미지로 대체됩니다.\n"}
                    active_video_engine = "none"

            yield {"data": "PROG|10\n"}
            # YouTube URL 자동 감지 + topic 교체
            ref_url = req.referenceUrl
            _topic = topic  # 외부 스코프 변수를 로컬로 복사
            _topic, ref_url = resolve_youtube_topic(_topic, ref_url)
            if _topic != topic:
                yield {"data": f"[레퍼런스 분석] YouTube 주제 추출 완료: '{_topic.split(chr(10))[0]}'\n"}

            yield {"data": f"[기획 전문가] '{_topic.split(chr(10))[0]}' 쇼츠 기획 시작... ({provider_label} 엔진)\n"}

            # 단계 1: LLM 기획 (Gemini / ChatGPT / Claude 선택)
            # Gemini 프로바이더일 때 키 로테이션 적용
            # Vertex AI: SA 인증 → 키 불필요
            if os.getenv("GEMINI_BACKEND") == "vertex_ai" and llm_provider == "gemini":
                llm_key_for_request = None
            else:
                llm_key_for_request = get_google_key(llm_key_override, extra_keys=gemini_keys_override) if llm_provider == "gemini" else llm_key_override
            loop = asyncio.get_running_loop()
            cuts, topic_folder, video_title, video_tags, video_desc, _fact_ctx = await loop.run_in_executor(
                None,
                lambda: generate_cuts(
                    _topic,
                    api_key_override=api_key_override,
                    lang=language,
                    llm_provider=llm_provider,
                    llm_key_override=llm_key_for_request,
                    channel=req.channel,
                    llm_model=llm_model_override,
                    reference_url=ref_url,
                    format_type=req.formatType,
                ),
            )

            # 테스트 모드: 컷 수 제한
            if req.maxCuts and len(cuts) > req.maxCuts:
                cuts = cuts[:req.maxCuts]
                yield {"data": f"[테스트 모드] {req.maxCuts}컷으로 제한\n"}

            yield {"data": "PROG|30\n"}
            yield {"data": f"[기획 완료] 총 {len(cuts)}컷 기획 완료!\n"}

            # ── workflowMode=review: 컷 생성 직후 끊고 초안 저장 ──
            if req.workflowMode == "review":
                from modules.utils.batch import add_job as _batch_add, update_job as _batch_update
                from modules.utils.batch import _compute_hash as _batch_hash
                _review_topic = _topic.split("\n\n[원본 영상 내용]")[0].strip()
                _review_job_id = _batch_add(
                    topic=_review_topic,
                    language=language,
                    camera_style=req.cameraStyle,
                    bgm_theme=req.bgmTheme,
                    llm_provider=llm_provider,
                    video_engine=video_engine,
                    image_engine=image_engine,
                    channel=req.channel,
                )
                # DB에 생성 결과 저장
                _all_scripts = " ".join(c.get("script", "") for c in cuts)
                _batch_update(_review_job_id,
                    draft_title=video_title,
                    draft_tags=json.dumps(video_tags, ensure_ascii=False),
                    draft_cuts_json=json.dumps(cuts, ensure_ascii=False),
                    script_hash=_batch_hash(_all_scripts),
                )
                review_payload = {
                    "job_id": _review_job_id,
                    "topic": _review_topic,
                    "title": video_title,
                    "tags": video_tags,
                    "cuts": cuts,
                    "topic_folder": topic_folder,
                    "status": "draft",
                    "prompt_status": "draft",
                    "fact_check_status": "pending",
                    "workflow_mode": "review",
                    "script_version": 1,
                    "prompt_version": 1,
                    "script_hash": _batch_hash(_all_scripts),
                }
                review_json_path = os.path.join("assets", topic_folder, "review_draft.json")
                os.makedirs(os.path.dirname(review_json_path), exist_ok=True)
                with open(review_json_path, "w", encoding="utf-8") as f:
                    json.dump(review_payload, f, ensure_ascii=False, indent=2)
                yield {"data": f"INFO|검수용 초안 생성 완료 (job_id={_review_job_id})\n"}
                yield {"data": f"REVIEW_READY|{json.dumps(review_payload, ensure_ascii=False)}\n"}
                yield {"data": "PROG|100\n"}
                generation_completed = True
                yield {"data": f"DONE|{topic_folder}\n"}
                return

            # 취소 체크포인트 1: LLM 기획 후
            if _is_cancelled():
                generation_cancelled = True
                yield {"data": "WARN|[취소됨] 사용자에 의해 생성이 취소되었습니다.\n"}
                return

            # 단계 2 & 3: 이미지와 TTS 병렬 처리 (Threading)
            image_label = "Imagen 4" if image_engine == "imagen" else ("Gemini Nano" if image_engine == "nano_banana" else image_engine)
            # 음성 선택: 자동(주제 분석) > 프론트엔드 직접 선택 > 채널 설정 > 기본값
            channel_voice_id = None
            channel_voice_settings = None
            if req.voiceId == "auto":
                channel_voice_id = _auto_select_voice(_topic, language)
                yield {"data": f"[음성 자동 선택] 주제 분석 → {_voice_name(channel_voice_id)}\n"}
            elif req.voiceId:
                channel_voice_id = req.voiceId  # 프론트엔드에서 선택한 음성
            if not channel_voice_id:
                channel_preset = get_channel_preset(req.channel)
                if channel_preset:
                    channel_voice_id = channel_preset.get("voice_id")
                    channel_voice_settings = channel_preset.get("voice_settings")
            else:
                # voice_id가 자동/수동 선택되어도 채널 voice_settings는 적용
                _preset = get_channel_preset(req.channel)
                if _preset:
                    channel_voice_settings = _preset.get("voice_settings")

            yield {"data": f"[생성 엔진] 아트 디렉터({image_label})와 성우(TTS) 동시 작업 중...\n"}

            visual_paths = [None] * len(cuts)
            audio_paths = [None] * len(cuts)
            word_timestamps_list = [None] * len(cuts)
            for cut in cuts:
                cut["script"] = prepare_spoken_script(cut.get("script", ""), language)
            scripts = [cut["script"] for cut in cuts]

            video_target_indices = set(range(len(cuts)))
            if video_model_override == "hero-only":
                video_target_indices = set(pick_hero_indices(cuts, req.formatType))
            if active_video_engine != "none" and video_model_override == "hero-only":
                label = ", ".join(str(i + 1) for i in sorted(video_target_indices)) or "-"
                yield {"data": f"[비디오] hero-only 모드 — Veo 대상 컷: {label} (나머지는 Ken Burns)\n"}

            # 이미지 엔진에 따라 생성 함수 선택
            gen_image_fn = generate_image_imagen if image_engine == "imagen" else generate_image_dalle

            def _get_image_key():
                """이미지 생성 시마다 다른 키 사용 (로테이션)"""
                if image_engine == "imagen":
                    return get_google_key(llm_key_override, service="imagen", extra_keys=gemini_keys_override)
                return api_key_override

            def process_cut(i, cut):
                # 취소 체크: 작업 시작 전
                if _is_cancelled():
                    return i, None, None, [], ["취소됨"]

                # 에러 수집 (SSE로 전달할 상세 정보) — 멀티스레드 안전
                errors = []
                errors_lock = threading.Lock()

                # 이미지 생성 (세마포어로 동시성 제한)
                img_path = None
                ab_variants = []
                with image_semaphore:
                    try:
                        cut_image_key = _get_image_key()
                        if image_engine == "imagen":
                            img_path = gen_image_fn(cut["prompt"], i, topic_folder, cut_image_key, model_override=image_model_override, gemini_api_keys=gemini_keys_override, topic=_topic)
                        elif image_engine == "nano_banana":
                            img_path = generate_image_nano_banana(cut["prompt"], i, topic_folder, cut_image_key, gemini_api_keys=gemini_keys_override, topic=_topic)
                        else:
                            img_path = gen_image_fn(cut["prompt"], i, topic_folder, cut_image_key, topic=_topic)
                    except Exception as exc:
                        # 폴백 체인: Imagen → Nano Banana (DALL-E 미사용)
                        if image_engine == "imagen":
                            print(f"[컷 {i+1} Imagen 실패 → Nano Banana 폴백] {exc}")
                            try:
                                _nb_key = get_google_key(llm_key_override, service="nano_banana", extra_keys=gemini_keys_override)
                                img_path = generate_image_nano_banana(cut["prompt"], i, topic_folder, _nb_key, gemini_api_keys=gemini_keys_override, topic=_topic)
                            except Exception as nb_exc:
                                with errors_lock:
                                    errors.append(f"이미지: Imagen+Nano Banana 전체 실패: {nb_exc}")
                                print(f"[컷 {i+1} Nano Banana도 실패] {nb_exc}")
                        else:
                            with errors_lock:
                                errors.append(f"이미지: {exc}")
                            print(f"[컷 {i+1} 이미지 생성 실패] {exc}")

                # 컷1 A/B 테스트: 구조화된 3가지 구도 변형 (조회율 최적화)
                # A(원본): 기본 프롬프트 그대로
                # B: 클로즈업 중심 (extreme scale 강조)
                # C: 와이드 + 스케일 비교 (콘텍스트 강조)
                if i == 0 and img_path:
                    ab_variants = []
                    original_prompt = cut["prompt"]
                    variant_suffixes = [
                        ", extreme close-up shot, macro perspective, filling the entire frame, shallow depth of field",
                        ", ultra wide establishing shot, tiny human silhouette for scale comparison, dramatic deep perspective",
                    ]
                    for variant_idx, suffix in enumerate(variant_suffixes):
                        try:
                            variant_key = _get_image_key()
                            variant_filename_idx = 100 + variant_idx
                            variant_prompt = original_prompt.rstrip(". ,") + suffix
                            if image_engine == "imagen":
                                v_path = gen_image_fn(variant_prompt, variant_filename_idx, topic_folder, variant_key, model_override=image_model_override, gemini_api_keys=gemini_keys_override, topic=_topic)
                            elif image_engine == "nano_banana":
                                v_path = generate_image_nano_banana(variant_prompt, variant_filename_idx, topic_folder, variant_key, gemini_api_keys=gemini_keys_override, topic=_topic)
                            else:
                                v_path = gen_image_fn(variant_prompt, variant_filename_idx, topic_folder, variant_key, topic=_topic)
                            if v_path:
                                ab_variants.append(v_path)
                                label = "클로즈업" if variant_idx == 0 else "와이드+스케일"
                                print(f"  [A/B 테스트] 컷1 변형 {label} 생성 완료")
                        except Exception as ab_exc:
                            print(f"  [A/B 테스트] 컷1 변형 {variant_idx + 1} 실패 (무시): {ab_exc}")

                # 비디오 변환과 TTS를 threading으로 병렬 실행 (데드락 방지: 직접 스레드 사용)
                video_result = [None]  # mutable container for thread result
                tts_result = [None]
                whisper_result = [None]

                def _run_video():
                    try:
                        cut_video_key = get_google_key(llm_key_override, service=active_video_engine, extra_keys=gemini_keys_override)
                        # hero-only는 로직 플래그 — 실제 모델명으로 전달하지 않음
                        _actual_veo_model = None if video_model_override == "hero-only" else video_model_override
                        video_result[0] = generate_video_from_image(
                            img_path, cut["prompt"], i, topic_folder, active_video_engine, cut_video_key,
                            description=cut.get("description", ""),
                            veo_model=_actual_veo_model,
                            gemini_api_keys=gemini_keys_override,
                            format_type=req.formatType,
                            camera_style=req.cameraStyle,
                            use_hero_profile=video_model_override == "hero-only",
                        )
                    except Exception as exc:
                        with errors_lock:
                            errors.append(f"비디오: {exc}")
                        print(f"[컷 {i+1} 비디오 변환 실패] {exc}")

                def _run_tts_and_whisper():
                    """TTS 생성 후 바로 Whisper 타임스탬프 추출 (순차 but 동일 스레드)"""
                    try:
                        # 감정 태그 추출 (description에서)
                        _cut_emotion = None
                        _cut_desc = cut.get("description", cut.get("text", ""))
                        for _etag in ["SHOCK", "WONDER", "TENSION", "REVEAL", "URGENCY", "DISBELIEF", "IDENTITY", "CALM"]:
                            if f"[{_etag}]" in _cut_desc:
                                _cut_emotion = _etag
                                break
                        tts_result[0] = generate_tts(cut["script"], i, topic_folder, elevenlabs_key_override, language=language, speed=req.ttsSpeed, voice_id=channel_voice_id, voice_settings=channel_voice_settings, emotion=_cut_emotion, channel=req.channel, already_prepared=True)
                    except Exception as exc:
                        with errors_lock:
                            errors.append(f"TTS: {exc}")
                        print(f"[컷 {i+1} TTS 생성 실패] {exc}")
                        return
                    # TTS 성공 시 LUFS 정규화 → Whisper 실행 (비디오 생성과 병렬)
                    if tts_result[0]:
                        try:
                            tts_result[0] = normalize_audio_lufs(tts_result[0])
                        except Exception as exc:
                            print(f"[컷 {i+1} LUFS 정규화 경고] {exc}")
                        try:
                            _raw_timestamps = generate_word_timestamps(tts_result[0], api_key_override, language=language)
                            # Whisper 재인식 오류 보정: 원본 스크립트 텍스트로 매핑
                            from modules.transcription.whisper import align_words_with_script
                            whisper_result[0] = align_words_with_script(_raw_timestamps, cut.get("script", ""))
                        except Exception as exc:
                            with errors_lock:
                                errors.append(f"타임스탬프: {exc}")
                            print(f"[컷 {i+1} 타임스탬프 추출 실패] {exc}")

                threads = []
                # 비디오 생성 여부 결정
                _should_video = False
                if img_path and active_video_engine != "none":
                    if video_model_override == "hero-only":
                        if i in video_target_indices:
                            _should_video = True
                        else:
                            print(f"[컷 {i+1}] 히어로 컷 아님 → Ken Burns 사용")
                    else:
                        # 전체 비디오 모드
                        _should_video = True
                if _should_video:
                    t = threading.Thread(target=_run_video, name=f"video-cut{i}", daemon=True)
                    t.start()
                    threads.append(t)
                t_tts = threading.Thread(target=_run_tts_and_whisper, name=f"tts-cut{i}", daemon=True)
                t_tts.start()
                threads.append(t_tts)

                # 완료 대기 (비디오: 최대 5분, TTS+Whisper: 최대 2분)
                for t in threads:
                    timeout = 300 if "video" in t.name.lower() else 120
                    t.join(timeout=timeout)
                    if t.is_alive():
                        with errors_lock:
                            errors.append(f"타임아웃: {t.name} 스레드가 {timeout}초 내 완료되지 않음")
                        print(f"[컷 {i+1} 타임아웃] {t.name} 스레드가 응답 없음")

                final_visual_path = video_result[0] if video_result[0] else img_path
                words = whisper_result[0] or []
                return i, final_visual_path, tts_result[0], words, errors, ab_variants if i == 0 else []

            tasks = [loop.run_in_executor(cut_executor, process_cut, i, cut) for i, cut in enumerate(cuts)]
            completed_count = 0

            all_cut_errors: dict[int, list[str]] = {}
            cut1_ab_variants: list[str] = []

            for future in asyncio.as_completed(tasks):
                i, final_visual_path, aud_path, words, errors, ab_vars = await future
                visual_paths[i] = final_visual_path
                audio_paths[i] = aud_path
                word_timestamps_list[i] = words
                if errors:
                    all_cut_errors[i + 1] = errors
                if i == 0 and ab_vars:
                    cut1_ab_variants = ab_vars

                completed_count += 1
                prog = 30 + int(50 * (completed_count / len(cuts)))
                yield {"data": f"PROG|{prog}\n"}

                engine_label = active_video_engine if active_video_engine != "none" else "이미지"
                if final_visual_path and aud_path:
                    yield {"data": f"  -> 컷 {i+1} 시각 소스({engine_label}/{image_label}) 및 음성 생성 완료\n"}
                else:
                    fail_parts = []
                    if not final_visual_path:
                        fail_parts.append("이미지")
                    if not aud_path:
                        fail_parts.append("음성")
                    err_detail = f" ({errors[0]})" if errors else ""
                    yield {"data": f"WARN|  -> 컷 {i+1} {'+'.join(fail_parts)} 생성 실패{err_detail}\n"}

            # 취소 체크포인트 2: 컷 생성 후
            if _is_cancelled():
                generation_cancelled = True
                yield {"data": "WARN|[취소됨] 사용자에 의해 생성이 취소되었습니다.\n"}
                return

            failed_visual = [i+1 for i, p in enumerate(visual_paths) if p is None]
            failed_audio = [i+1 for i, p in enumerate(audio_paths) if p is None]
            if failed_visual or failed_audio:
                details = []
                if failed_visual:
                    details.append(f"이미지 실패: 컷 {failed_visual}")
                if failed_audio:
                    details.append(f"오디오 실패: 컷 {failed_audio}")
                # 첫 번째 에러 상세 정보 포함
                first_err = next(iter(all_cut_errors.values()), [])
                err_hint = f" 원인: {first_err[0]}" if first_err else ""
                yield {"data": f"ERROR|[소스 생성 오류] {', '.join(details)}.{err_hint}\n"}
                return

            # 취소 체크포인트 3: 렌더링 시작 전
            if _is_cancelled():
                generation_cancelled = True
                yield {"data": "WARN|[취소됨] 사용자에 의해 생성이 취소되었습니다.\n"}
                return

            yield {"data": "PROG|85\n"}

            platform_label = ", ".join(p.upper() for p in req.platforms)
            yield {"data": f"[렌더링 마스터] Remotion 렌더링 시작 — 플랫폼: {platform_label}\n"}

            # 단계 4: Remotion 비디오 렌더링 (멀티 플랫폼 지원)
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
                        camera_style=req.cameraStyle,
                        bgm_theme=req.bgmTheme,
                        channel=req.channel,
                        platforms=req.platforms,
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
                yield {"data": "ERROR|[Remotion 오류] 영상 렌더링에 실패했습니다. remotion 폴더에서 'npm install'이 완료되었는지 확인해주세요.\n"}
                return

            # 멀티 플랫폼: dict, 단일: str → 통일 처리
            if isinstance(render_result, str):
                video_paths_map = {"youtube": render_result}
            else:
                video_paths_map = render_result

            # 대표 영상 (첫 번째 = 주 플랫폼)
            primary_platform = list(video_paths_map.keys())[0]
            video_path = video_paths_map[primary_platform]
            final_abs_path = os.path.abspath(video_path)

            if not os.path.exists(final_abs_path):
                yield {"data": f"ERROR|[파일 오류] 렌더링 성공 응답을 받았지만 파일이 없습니다: {final_abs_path}\n"}
                return

            # 스마트 썸네일 자동 생성 (업로드용)
            thumbnail_path = None
            try:
                from modules.utils.thumbnail import select_best_thumbnail, create_thumbnail
                best_img = select_best_thumbnail(visual_paths)
                if best_img:
                    thumb_dir = os.path.join("assets", topic_folder, "video")
                    thumb_output = os.path.join(thumb_dir, "thumbnail.jpg")
                    thumbnail_path = create_thumbnail(best_img, thumb_output)
            except Exception as thumb_err:
                print(f"[썸네일 경고] 자동 생성 실패: {thumb_err}")

            yield {"data": "PROG|100\n"}

            # 사용자 지정 저장 경로가 있으면 복사 (경로 검증 포함)
            if output_path:
                from pathlib import Path as _P
                abs_output = os.path.realpath(output_path)
                safe_base = os.path.realpath("assets")
                home_dir = os.path.realpath(os.path.expanduser("~"))
                dl_dir = os.path.realpath(os.environ.get("DOWNLOAD_DIR", os.path.join(home_dir, "Downloads")))
                path_ok = False
                for base in [safe_base, home_dir, dl_dir]:
                    try:
                        _P(abs_output).relative_to(base)
                        path_ok = True
                        break
                    except ValueError:
                        continue
                if not path_ok:
                    yield {"data": "ERROR|[보안 오류] 지정 경로가 허용 범위(assets/ 또는 홈 디렉토리)를 벗어납니다.\n"}
                else:
                    try:
                        out_dir = os.path.dirname(abs_output)
                        if out_dir:
                            os.makedirs(out_dir, exist_ok=True)
                        await asyncio.to_thread(shutil.copy2, final_abs_path, abs_output)
                        yield {"data": f"[저장] 지정 경로에 복사 완료: {abs_output}\n"}
                    except Exception as copy_err:
                        yield {"data": f"ERROR|[저장 오류] 지정 경로 복사 실패: {copy_err}\n"}

            # Downloads 폴더로 자동 복사: Downloads/토픽/채널명.mp4
            _dl_base = os.environ.get("DOWNLOAD_DIR", os.path.join(os.path.expanduser("~"), "Downloads"))
            downloads_path = None
            if os.path.isdir(_dl_base):
                _dl_channel = req.channel or "default"
                _dl_dir = os.path.join(_dl_base, topic_folder)
                os.makedirs(_dl_dir, exist_ok=True)
                try:
                    dl_path = os.path.join(_dl_dir, f"{_dl_channel}.mp4")
                    await asyncio.to_thread(shutil.copy2, os.path.abspath(video_path), dl_path)
                    downloads_path = dl_path
                    yield {"data": f"[저장] Downloads/{topic_folder}/{_dl_channel}.mp4\n"}
                except Exception as cp_err:
                    print(f"[Downloads 복사 실패] {cp_err}")

            # 프론트엔드 라우팅용 경로 (StaticFiles mount 기준)
            final_filename = os.path.basename(video_path)
            relative_video_path = f"/assets/{topic_folder}/video/{final_filename}"

            platform_count = len(video_paths_map)
            if downloads_path and os.path.exists(downloads_path):
                if platform_count > 1:
                    yield {"data": f"[완료] {platform_count}개 플랫폼 영상 렌더링 대성공! 📂 Downloads 폴더에 저장됨\n"}
                else:
                    yield {"data": f"[완료] 최종 비디오 렌더링 대성공! 📂 Downloads 폴더에 저장됨: {final_filename}\n"}
            else:
                yield {"data": f"[완료] 최종 비디오 렌더링 대성공! 경로: {relative_video_path}\n"}
            # 썸네일 경로도 함께 전달 (업로드 시 사용)
            thumb_relative = ""
            if thumbnail_path and os.path.exists(thumbnail_path):
                thumb_relative = f"/assets/{topic_folder}/video/thumbnail.jpg"

            # ── 자동 업로드: 채널 선택 시 publishMode에 따라 플랫폼 업로드 ──
            if req.channel and req.publishMode != "local":
                from modules.utils.channel_config import get_upload_account
                upload_preset = get_channel_preset(req.channel)
                upload_platforms = upload_preset.get("platforms", []) if upload_preset else []
                abs_video_path = os.path.abspath(video_path)

                # publishMode → privacy 매핑
                if req.publishMode == "realtime":
                    yt_privacy = "public"
                    tt_privacy = "PUBLIC_TO_EVERYONE"
                elif req.publishMode == "private":
                    yt_privacy = "private"
                    tt_privacy = "SELF_ONLY"
                elif req.publishMode == "scheduled":
                    yt_privacy = "private"  # 예약은 private + publishAt
                    tt_privacy = "SELF_ONLY"
                else:
                    yt_privacy = "private"
                    tt_privacy = "SELF_ONLY"

                # 예약 시간 파싱
                yt_publish_at = None
                tt_schedule_time = None
                if req.publishMode == "scheduled" and req.scheduledTime:
                    from datetime import datetime, timezone
                    try:
                        sched_dt = datetime.fromisoformat(req.scheduledTime)
                        if sched_dt.tzinfo is None:
                            sched_dt = sched_dt.replace(tzinfo=timezone.utc)
                        yt_publish_at = sched_dt.isoformat()
                        tt_schedule_time = int(sched_dt.timestamp())
                    except ValueError:
                        yield {"data": f"WARN|예약 시간 형식 오류: {req.scheduledTime}\n"}

                upload_results = []
                for plat in upload_platforms:
                    account_id = get_upload_account(req.channel, plat)
                    try:
                        if plat == "youtube":
                            from modules.upload.youtube import upload_video as yt_upload
                            yield {"data": f"[업로드] YouTube 자동 업로드 시작... ({yt_privacy})\n"}
                            yt_result = await asyncio.get_running_loop().run_in_executor(
                                cut_executor,
                                lambda: yt_upload(
                                    video_path=abs_video_path,
                                    title=video_title,
                                    description="\n".join(s.strip() for s in scripts if s.strip()),
                                    tags=[t.lstrip("#") for t in video_tags] + [req.channel, language],
                                    privacy=yt_privacy,
                                    channel_id=account_id,
                                    publish_at=yt_publish_at,
                                    format_type=req.formatType,
                                    series_title=req.seriesTitle,
                                    channel=req.channel or "",
                                )
                            )
                            if yt_result.get("success"):
                                url = yt_result.get("url", "")
                                sched_info = f" (예약: {yt_publish_at})" if yt_publish_at else ""
                                yield {"data": f"UPLOAD_DONE|youtube|{url}{sched_info}\n"}
                                upload_results.append({"platform": "youtube", "url": url})
                            else:
                                yield {"data": f"WARN|YouTube 업로드 실패: {yt_result.get('error', 'unknown')}\n"}
                        elif plat == "tiktok":
                            from modules.upload.tiktok import upload_video as tt_upload
                            yield {"data": f"[업로드] TikTok 자동 업로드 시작... ({tt_privacy})\n"}
                            tt_result = await asyncio.get_running_loop().run_in_executor(
                                cut_executor,
                                lambda: tt_upload(
                                    video_path=abs_video_path,
                                    title=video_title[:150],
                                    privacy_level=tt_privacy,
                                    user_id=account_id,
                                    schedule_time=tt_schedule_time,
                                )
                            )
                            if tt_result.get("success"):
                                sched_info = f" (예약: {tt_schedule_time})" if tt_schedule_time else ""
                                yield {"data": f"UPLOAD_DONE|tiktok|{sched_info}\n"}
                                upload_results.append({"platform": "tiktok"})
                            else:
                                yield {"data": f"WARN|TikTok 업로드 실패\n"}
                    except PermissionError:
                        yield {"data": f"WARN|{plat.upper()} 인증 필요 — 설정에서 계정을 연동해주세요\n"}
                    except Exception as upload_err:
                        safe_err = re.sub(r"(AIza|sk-|key=|token=|Bearer )[A-Za-z0-9_\-]{4,}", r"\1***", str(upload_err)[:150])
                        yield {"data": f"WARN|{plat.upper()} 업로드 실패: {safe_err}\n"}

            # 비용 추적 (단일 생성 경로)
            try:
                from modules.utils.cost_tracker import calc_llm_cost
                _n_cuts = len(cuts) if cuts else 0
                _llm_model = req.llmModel or "gemini-2.5-pro"
                # LLM 토큰 추정: 시스템 프롬프트 ~10K + 검증/강화 ~5K, 출력 ~500/cut
                _est_input = 15000 + _n_cuts * 500
                _est_output = _n_cuts * 500
                _llm_usd = calc_llm_cost(_llm_model, _est_input, _est_output)
            except Exception:
                _n_cuts = len(cuts) if cuts else 0
                _llm_usd = 0.0
            _record_generation_cost_once(
                success=True,
                llm_usd=_llm_usd,
                image_count=_n_cuts + len(cut1_ab_variants if "cut1_ab_variants" in locals() else []),
                video_count=(
                    sum(
                        1 for p in visual_paths
                        if str(p or "").lower().split("?")[0].endswith((".mp4", ".webm", ".mov"))
                    ) if active_video_engine != "none" else 0
                ),
                video_model=os.getenv("VEO_MODEL") or video_model_override,
                tts_chars=sum(len(s) for s in scripts if s),
            )
            generation_completed = True

            yield {"data": f"DONE|{relative_video_path}|{thumb_relative}\n"}

          except Exception as e:
            traceback.print_exc()
            err_str = str(e)
            if "401" in err_str or "invalid_api_key" in err_str or "Incorrect API key" in err_str:
                yield {"data": "ERROR|[인증 오류] API 키가 만료되었거나 유효하지 않습니다. .env 파일의 키를 확인하거나, 프론트엔드에서 새 키를 입력해주세요.\n"}
            elif "429" in err_str or "rate_limit" in err_str or "quota" in err_str:
                yield {"data": "ERROR|[할당량 초과] API 사용량 한도에 도달했습니다. 잠시 후 다시 시도하거나 요금제를 확인해주세요.\n"}
            elif "timeout" in err_str.lower() or "timed out" in err_str.lower():
                yield {"data": "ERROR|[타임아웃] API 응답 시간이 초과되었습니다. 네트워크 상태를 확인하고 다시 시도해주세요.\n"}
            elif "connection" in err_str.lower() or "network" in err_str.lower():
                yield {"data": "ERROR|[네트워크 오류] API 서버에 연결할 수 없습니다. 인터넷 연결을 확인해주세요.\n"}
            else:
                # 원시 예외에 API 키 파편이 포함될 수 있으므로 마스킹
                safe_msg = re.sub(r"(AIza|sk-|key=|token=|Bearer )[A-Za-z0-9_\-]{4,}", r"\1***", err_str[:200])
                yield {"data": f"ERROR|[시스템 오류] {safe_msg}\n"}
          finally:
            if not generation_completed and not generation_cancelled:
                _record_generation_cost_once(success=False)
            # 작업 완료/취소 후 정리
            with generation_lock:
                active_generation_ids.discard(generation_id)
                cancel_events.pop(generation_id, None)

    return EventSourceResponse(sse_generator())


# ── v2 오케스트라 파이프라인 ──────────────────────────────────────

@router.post("/api/generate/v2")
async def generate_video_v2(req: GenerateRequest):
    """오케스트라 기반 영상 생성 파이프라인 (v2).

    동일한 SSE 프로토콜 사용 (PROG|, WARN|, ERROR|, DONE|, UPLOAD_DONE|).
    에이전트별 모델 자동 분배 + 토큰 추적.
    """
    from modules.orchestrator.orchestrator import MainOrchestrator
    from modules.orchestrator.base import AgentContext
    from modules.utils.channel_config import get_channel_preset

    # 채널 프리셋 fallback
    tts_speed = req.ttsSpeed
    camera_style = req.cameraStyle
    voice_id = req.voiceId
    voice_settings = None
    caption_size = req.captionSize
    caption_y = req.captionY
    if req.channel:
        _ch_preset = get_channel_preset(req.channel)
        if _ch_preset:
            if _ch_preset.get("tts_speed") is not None:
                tts_speed = _ch_preset["tts_speed"]
            if _ch_preset.get("caption_size"):
                caption_size = _ch_preset["caption_size"]
            if _ch_preset.get("caption_y"):
                caption_y = _ch_preset["caption_y"]
            if not voice_id:
                voice_id = _ch_preset.get("voice_id")
                voice_settings = _ch_preset.get("voice_settings")

    ctx = AgentContext(
        topic=req.topic,
        language=req.language,
        channel=req.channel,
        reference_url=req.referenceUrl,
        llm_provider=req.llmProvider,
        llm_model=req.llmModel,
        llm_key=req.llmKey,
        image_engine=req.imageEngine,
        image_model=req.imageModel,
        video_engine=req.videoEngine,
        video_model=req.videoModel,
        voice_id=voice_id,
        voice_settings=voice_settings,
        tts_speed=tts_speed,
        camera_style=camera_style,
        bgm_theme=req.bgmTheme,
        platforms=req.platforms,
        caption_size=caption_size,
        caption_y=caption_y,
        publish_mode=req.publishMode,
        scheduled_time=req.scheduledTime,
        workflow_mode=req.workflowMode,
        max_cuts=req.maxCuts,
        api_key_override=req.apiKey,
        elevenlabs_key=req.elevenlabsKey,
        gemini_keys_override=req.geminiKeys,
        format_type=req.formatType,
    )

    orchestrator = MainOrchestrator()

    async def sse_stream():
        async for msg in orchestrator.run(ctx):
            yield {"data": msg}

    return EventSourceResponse(sse_stream())
