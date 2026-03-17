import os
import sys
import io
import re
import shutil
import asyncio
import threading
import traceback
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
load_dotenv(override=True)

from modules.gpt.cutter import generate_cuts
from modules.image.dalle import generate_image as generate_image_dalle
from modules.image.imagen import generate_image_imagen
from modules.video.engines import generate_video_from_image, get_available_engines, check_engine_available
from modules.tts.elevenlabs import generate_tts, check_quota as check_elevenlabs_quota
from modules.transcription.whisper import generate_word_timestamps
from modules.video.remotion import create_remotion_video
from modules.utils.constants import PROVIDER_LABELS
from modules.utils.keys import get_google_key, count_google_keys, count_available_keys, get_key_usage_stats, get_service_usage_totals
from modules.utils.models import MODEL_RATE_LIMITS
from modules.utils.audio import normalize_audio_lufs
from modules.utils.channel_config import get_channel_preset, get_channel_names, get_cost_tier, get_cost_tier_names, get_master_style, COST_TIERS

@asynccontextmanager
async def _lifespan(app):
    yield
    _cut_executor.shutdown(wait=False)

app = FastAPI(lifespan=_lifespan)

# 동시 생성 요청 제한 (GPU/API 과부하 방지)
# 모델/키 오버라이드는 함수 파라미터로 전달 — os.environ 미사용으로 동시 요청 안전
_generate_semaphore = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENT_GENERATE", "1")))
# 컷 병렬 처리용 공유 스레드풀 (요청마다 생성/삭제 방지)
_cut_executor = ThreadPoolExecutor(max_workers=4)
# 이미지 동시 생성 제한 (모듈 레벨 — MAX_CONCURRENT_GENERATE > 1 에서도 전역 제한)
_image_semaphore = threading.Semaphore(3)

# 에러 메시지 키 마스킹 헬퍼 (API 키 노출 방지)
_KEY_MASK_RE = re.compile(r"(AIza|sk-|key=|token=|Bearer )[A-Za-z0-9_\-]{4,}")
def _mask_error(e: Exception, max_len: int = 200) -> str:
    return _KEY_MASK_RE.sub(r"\1***", str(e)[:max_len])

# 취소 토큰: 요청별 이벤트 (generation_id → (Event, created_time))
_cancel_events: dict[str, tuple[threading.Event, float]] = {}
_active_generation_id: str | None = None
_generation_lock = threading.Lock()
_CANCEL_EVENT_TTL = 120  # 2분 후 미정리 이벤트 자동 삭제 (SSE 끊김 시 빠른 정리)

# ElevenLabs 쿼터 캐시 (매 요청 HTTP 호출 방지, 키별 캐시)
_elevenlabs_quota_cache: dict[str, tuple[float, dict | None]] = {}  # key_hash → (timestamp, quota_info)
_elevenlabs_quota_lock = threading.Lock()
_ELEVENLABS_QUOTA_TTL = 60  # 60초 캐시


@app.get("/")
async def root():
    return {
        "status": "running",
        "name": "AskAnything Video Generator API",
        "endpoints": {
            "POST /api/generate": "비디오 생성 (SSE 스트리밍)",
            "GET /api/engines": "사용 가능한 비디오 엔진 목록",
        },
    }


# 정적 파일 서빙 (비디오 다운로드용)
os.makedirs("assets", exist_ok=True)
app.mount("/assets", StaticFiles(directory="assets"), name="assets")

# CORS 설정 (프론트엔드 연동)
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:3001,http://localhost:8080,http://127.0.0.1:3000").split(",")
# 개발 환경: 와일드카드 포함 시 모든 origin 허용
if "*" in _cors_origins:
    _cors_origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════ 자동 음성 선택 ═══════════════════════

# ElevenLabs premade voice IDs
_VOICE_MAP = {
    "eric":    "cjVigY5qzO86Huf0OWal",  # 차분/다큐
    "adam":    "pNInz6obpgDQGcFmaJgB",  # 깊은/권위
    "brian":   "nPczCjzI2devNBz1zQrb",  # 내레이션
    "bill":    "pqHfZKP75CvOlQylNhV4",  # 다큐/진지
    "daniel":  "onwK4e9ZLuTAKqWW03F9",  # 뉴스/정보
    "rachel":  "21m00Tcm4TlvDq8ikWAM",  # 차분/여성
    "sarah":   "EXAVITQu4vr4xnSDxMaL",  # 부드러운
    "matilda": "XrExE9yKIg1WjnnlVkGX",  # 따뜻한
    "charlie": "IKne3meq5aSn9XLyUdCD",  # 유머/캐주얼
    "antoni":  "ErXwobaYiN019PkySvjV",  # 만능
    "george":  "JBFqnCBsd6RMkjVDRZzb",  # 거친/공포
}

_VOICE_ID_TO_NAME = {v: k.capitalize() for k, v in _VOICE_MAP.items()}

# 주제 키워드 → 최적 음성 매핑 (우선순위 순)
_TONE_RULES: list[tuple[list[str], str]] = [
    # 공포/미스터리/범죄
    (["공포", "호러", "귀신", "유령", "살인", "미스터리", "괴담", "소름", "horror", "ghost", "murder", "creepy", "dark", "죽음", "저주", "심령", "폐허"], "george"),
    # 유머/재미/밈
    (["웃긴", "유머", "밈", "meme", "funny", "코미디", "개그", "ㅋㅋ", "레전드", "웃음", "드립", "짤"], "charlie"),
    # 과학/기술/교육
    (["과학", "기술", "AI", "인공지능", "우주", "NASA", "양자", "물리", "화학", "생물", "science", "tech", "quantum", "로봇", "컴퓨터", "프로그래밍"], "daniel"),
    # 역사/다큐
    (["역사", "전쟁", "고대", "조선", "제국", "세계대전", "history", "ancient", "war", "왕조", "문명", "유적"], "bill"),
    # 감성/힐링/동기부여
    (["감동", "힐링", "동기부여", "motivation", "inspiring", "감성", "위로", "희망", "사랑", "인생", "명언"], "matilda"),
    # 뉴스/시사/경제
    (["뉴스", "시사", "경제", "정치", "주식", "투자", "부동산", "금리", "인플레이션", "news", "economy", "stock", "비트코인", "코인"], "adam"),
    # 자연/동물/여행
    (["자연", "동물", "여행", "바다", "산", "nature", "animal", "travel", "풍경", "safari", "ocean"], "sarah"),
]


def _auto_select_voice(topic: str, language: str = "ko") -> str:
    """주제 키워드를 분석하여 최적의 ElevenLabs 음성을 자동 선택합니다."""
    topic_lower = topic.lower()
    for keywords, voice_name in _TONE_RULES:
        for kw in keywords:
            if kw.lower() in topic_lower:
                print(f"[음성 자동 선택] '{kw}' 매칭 → {voice_name} ({_VOICE_MAP[voice_name][:12]}...)")
                return _VOICE_MAP[voice_name]
    # 기본값: Eric (차분한 다큐 톤, 만능)
    return _VOICE_MAP["eric"]


def _voice_name(voice_id: str) -> str:
    """음성 ID를 이름으로 변환합니다."""
    return _VOICE_ID_TO_NAME.get(voice_id, voice_id[:12] + "...")


class GenerateRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    apiKey: str | None = None
    elevenlabsKey: str | None = None
    videoEngine: str = "none"
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
    channel: str | None = None  # 채널별 인트로/아웃트로: "askanything", "wonderdrop" 등
    platforms: list[str] = ["youtube"]  # 렌더 플랫폼: "youtube", "tiktok", "reels"
    ttsSpeed: float = Field(0.9, ge=0.5, le=2.0)  # TTS 속도: 0.7(느림) ~ 1.0(기본) ~ 1.2(빠름)
    voiceId: str | None = None  # ElevenLabs 음성 ID
    mode: str = "production"  # "draft" = 비디오 생성 스킵 (Ken Burns만), "production" = 풀 파이프라인
    captionSize: int = Field(48, ge=32, le=72)  # 자막 폰트 크기 (px)
    captionY: int = Field(28, ge=10, le=50)  # 자막 높이 (%): 하단 기준
    referenceUrl: str | None = None  # YouTube 레퍼런스 URL (분석 후 스타일 반영)
    costTier: str | None = None  # 비용 프리셋: "free", "standard", "premium" (설정 시 엔진 자동 결정)

    @field_validator("language")
    @classmethod
    def valid_language(cls, v: str) -> str:
        allowed = {"ko", "en", "de", "da", "no", "es", "fr", "pt", "it", "nl", "sv", "pl", "ru", "ja", "zh", "ar", "tr", "hi"}
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
        allowed = {"kling", "sora2", "veo3", "none"}
        if v not in allowed:
            raise ValueError(f"지원하지 않는 비디오 엔진: {v}. 허용: {allowed}")
        return v

    @field_validator("imageEngine")
    @classmethod
    def valid_image_engine(cls, v: str) -> str:
        allowed = {"dalle", "imagen"}
        if v not in allowed:
            raise ValueError(f"지원하지 않는 이미지 엔진: {v}. 허용: {allowed}")
        return v

    @field_validator("llmProvider")
    @classmethod
    def valid_llm_provider(cls, v: str) -> str:
        allowed = {"openai", "gemini", "claude"}
        if v not in allowed:
            raise ValueError(f"지원하지 않는 LLM 프로바이더: {v}. 허용: {allowed}")
        return v

    @field_validator("mode")
    @classmethod
    def valid_mode(cls, v: str) -> str:
        if v not in {"production", "draft"}:
            raise ValueError(f"지원하지 않는 모드: {v}. 허용: production, draft")
        return v

    @field_validator("cameraStyle")
    @classmethod
    def valid_camera_style(cls, v: str) -> str:
        allowed = {"auto", "dynamic", "gentle", "static"}
        if v not in allowed:
            raise ValueError(f"지원하지 않는 카메라 스타일: {v}. 허용: {allowed}")
        return v

    @field_validator("platforms")
    @classmethod
    def valid_platforms(cls, v: list[str]) -> list[str]:
        allowed = {"youtube", "tiktok", "reels"}
        for p in v:
            if p not in allowed:
                raise ValueError(f"지원하지 않는 플랫폼: {p}. 허용: {allowed}")
        return v

    @field_validator("costTier")
    @classmethod
    def valid_cost_tier(cls, v: str | None) -> str | None:
        if v is None:
            return v
        allowed = set(get_cost_tier_names())
        if v not in allowed:
            raise ValueError(f"지원하지 않는 비용 티어: {v}. 허용: {allowed}")
        return v


@app.get("/api/cost-tiers")
async def list_cost_tiers():
    """비용 티어 프리셋 목록 반환."""
    return {name: {"label": t["label"], "estimated_cost": t["estimated_cost"]} for name, t in COST_TIERS.items()}


@app.get("/api/engines")
async def list_engines():
    return get_available_engines()


@app.get("/api/key-usage")
async def key_usage():
    """Google API 키별 사용량 통계 (세션 내 추적)."""
    stats = get_key_usage_stats()
    return {
        "total_keys": count_google_keys(),
        "keys": stats,
        "note": "서버 재시작 시 카운터가 초기화됩니다. Veo 3는 유료 계정 기준 일일 한도가 있습니다.",
    }


class AnalyzeShortsRequest(BaseModel):
    url: str = Field(..., min_length=5)


@app.post("/api/analyze-shorts")
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


@app.get("/api/health")
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
    from modules.utils.keys import get_all_google_keys, mask_key
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


@app.get("/api/model-limits")
async def model_limits():
    """모델별 Rate Limit + 잔여 호출 수를 반환합니다."""
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


def _validate_keys(api_key_override: str | None, elevenlabs_key_override: str | None, video_engine: str,
                    image_engine: str = "imagen", llm_provider: str = "gemini", llm_key_override: str | None = None) -> list[str]:
    """파이프라인 시작 전 필수 키 검증. 누락된 키 이름 목록을 반환."""
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

    # Imagen 사용 시 Google 키 필요
    if image_engine == "imagen":
        gemini_key = llm_key_override or os.getenv("GEMINI_API_KEY", "") or os.getenv("GOOGLE_API_KEY", "")
        if not gemini_key:
            errors.append("GEMINI_API_KEY (Imagen 4 이미지 생성에 필수)")

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


@app.post("/api/cancel")
async def cancel_generation():
    """현재 진행 중인 생성 작업을 취소합니다."""
    with _generation_lock:
        if _active_generation_id and _active_generation_id in _cancel_events:
            _cancel_events[_active_generation_id][0].set()
            print(f"[취소] 생성 작업 취소 요청: {_active_generation_id}")
            return {"status": "cancelled", "generation_id": _active_generation_id}
        return {"status": "idle", "message": "진행 중인 생성 작업이 없습니다."}


@app.get("/api/status")
async def generation_status():
    """현재 생성 상태 확인."""
    with _generation_lock:
        return {
            "active": _active_generation_id is not None,
            "generation_id": _active_generation_id,
        }


@app.post("/api/generate")
async def generate_video_endpoint(req: GenerateRequest):
    # 비용 티어 적용: costTier가 설정되면 엔진/모델 기본값을 프리셋으로 오버라이드
    if req.costTier:
        tier = get_cost_tier(req.costTier)
        if tier:
            # 사용자가 명시적으로 설정한 필드는 건드리지 않음 (Pydantic model_fields_set)
            _user_set = req.model_fields_set
            if "llmProvider" not in _user_set:
                req.llmProvider = tier.get("llm_provider", req.llmProvider)
            if "llmModel" not in _user_set:
                req.llmModel = tier.get("llm_model")
            if "imageEngine" not in _user_set:
                req.imageEngine = tier.get("image_engine", req.imageEngine)
            if "imageModel" not in _user_set:
                req.imageModel = tier.get("image_model")
            if "videoEngine" not in _user_set:
                req.videoEngine = tier.get("video_engine", req.videoEngine)

    topic = req.topic
    api_key_override = req.apiKey
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
        global _active_generation_id

        # 이전 작업 취소 + 새 작업 등록 (요청별 이벤트로 격리)
        import time as _t
        cancel_event = threading.Event()
        with _generation_lock:
            # 오래된 이벤트 정리 (메모리 누수 방지)
            now = _t.time()
            stale = [gid for gid, (_, ts) in _cancel_events.items() if now - ts > _CANCEL_EVENT_TTL]
            for gid in stale:
                _cancel_events.pop(gid, None)
            if _active_generation_id and _active_generation_id in _cancel_events:
                _cancel_events[_active_generation_id][0].set()
                print(f"[취소] 새 요청으로 이전 작업({_active_generation_id}) 자동 취소")
            _cancel_events[generation_id] = (cancel_event, now)
            _active_generation_id = generation_id

        def _is_cancelled() -> bool:
            return cancel_event.is_set()

        # 동시 요청 제한: 슬롯 부족 시 대기 안내
        if _generate_semaphore.locked():
            yield {"data": "WARN|[대기열] 다른 비디오가 생성 중입니다. 순서를 기다리는 중...\n"}
        async with _generate_semaphore:
          try:
            # 사전 검증: 필수 API 키 확인
            missing = _validate_keys(api_key_override, elevenlabs_key_override, video_engine, image_engine, llm_provider, llm_key_override)
            if missing:
                yield {"data": "ERROR|[환경 설정 오류] 다음 API 키가 누락되었거나 유효하지 않습니다:\n"}
                for m in missing:
                    yield {"data": f"ERROR|  - {m}\n"}
                yield {"data": "ERROR|.env 파일을 확인하거나, 프론트엔드에서 API Key를 입력해주세요.\n"}
                return

            # 사전 검증: API 쿼터 체크 (경고만, 차단 안 함, 키별 60초 캐시)
            import time as _time_mod, hashlib as _hl
            el_key = elevenlabs_key_override or os.getenv("ELEVENLABS_API_KEY", "")
            _el_key_hash = _hl.sha256(el_key.encode()).hexdigest()[:12] if el_key else ""
            quota_info = None
            with _elevenlabs_quota_lock:
                cached_q = _elevenlabs_quota_cache.get(_el_key_hash)
                if cached_q and _time_mod.time() - cached_q[0] < _ELEVENLABS_QUOTA_TTL:
                    quota_info = cached_q[1]
            if quota_info is None and el_key:
                quota_info = check_elevenlabs_quota(el_key)
                with _elevenlabs_quota_lock:
                    _elevenlabs_quota_cache[_el_key_hash] = (_time_mod.time(), quota_info)
            if quota_info:
                remaining = quota_info["remaining"]
                limit = quota_info["limit"]
                pct = (remaining / limit * 100) if limit > 0 else 0
                if remaining < 500:
                    yield {"data": f"WARN|[ElevenLabs 잔여 크레딧 부족] {remaining:,}/{limit:,}자 남음 ({pct:.0f}%). 생성이 중단될 수 있습니다.\n"}
                elif pct < 20:
                    yield {"data": f"WARN|[ElevenLabs 크레딧 경고] {remaining:,}/{limit:,}자 남음 ({pct:.0f}%).\n"}

            # Google 키 가용성 경고
            total_keys = count_google_keys(extra_keys=gemini_keys_override)
            avail_keys = count_available_keys(extra_keys=gemini_keys_override)
            if total_keys > 0 and avail_keys < total_keys:
                blocked_count = total_keys - avail_keys
                if avail_keys == 0:
                    yield {"data": f"WARN|[Google 키 경고] 모든 {total_keys}개 키가 429 차단됨. 쿼터 초과 가능성 높음.\n"}
                else:
                    yield {"data": f"WARN|[Google 키 상태] {avail_keys}/{total_keys}개 사용 가능 ({blocked_count}개 24시간 차단 중)\n"}

            provider_label = PROVIDER_LABELS.get(llm_provider, "ChatGPT")

            # 드래프트 모드: 비디오 생성 스킵 (Ken Burns만 사용, 빠른 미리보기)
            is_draft = getattr(req, 'mode', 'production') == 'draft'
            if is_draft:
                yield {"data": "[드래프트 모드] 비디오 생성 스킵 — Ken Burns 이미지만 사용합니다.\n"}

            # 비디오 엔진 변수 초기화 (아래에서 키 선택·사전 검증에 사용)
            active_video_engine = "none" if is_draft else video_engine

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
            # YouTube URL 자동 감지: referenceUrl이 없으면 topic에서 URL 추출
            _yt_pattern = re.compile(r"(?:youtube\.com/(?:shorts/|watch\?v=)|youtu\.be/)")
            ref_url = req.referenceUrl
            if not ref_url and _yt_pattern.search(topic):
                ref_url = topic
                yield {"data": "[레퍼런스 분석] YouTube URL 감지 — 영상 분석 후 스타일을 참고합니다\n"}

            yield {"data": f"[기획 전문가] '{topic}' 쇼츠 기획 시작... ({provider_label} 엔진)\n"}

            # 단계 1: LLM 기획 (Gemini / ChatGPT / Claude 선택)
            # Gemini 프로바이더일 때 키 로테이션 적용
            llm_key_for_request = get_google_key(llm_key_override, extra_keys=gemini_keys_override) if llm_provider == "gemini" else llm_key_override
            loop = asyncio.get_running_loop()
            cuts, topic_folder, video_title, video_tags, video_seo_desc = await loop.run_in_executor(
                None,
                lambda: generate_cuts(
                    topic,
                    api_key_override=api_key_override,
                    lang=language,
                    llm_provider=llm_provider,
                    llm_key_override=llm_key_for_request,
                    channel=req.channel,
                    llm_model=llm_model_override,
                    reference_url=ref_url,
                ),
            )

            yield {"data": "PROG|30\n"}
            yield {"data": f"[기획 완료] 총 {len(cuts)}컷 기획 완료!\n"}

            # 취소 체크포인트 1: LLM 기획 후
            if _is_cancelled():
                yield {"data": "WARN|[취소됨] 사용자에 의해 생성이 취소되었습니다.\n"}
                return

            # 단계 2 & 3: 이미지와 TTS 병렬 처리 (Threading)
            image_label = "Imagen 4" if image_engine == "imagen" else "DALL-E"
            # 음성 선택: 자동(주제 분석) > 프론트엔드 직접 선택 > 채널 설정 > 기본값
            channel_voice_id = None
            if req.voiceId == "auto":
                channel_voice_id = _auto_select_voice(req.topic, language)
                yield {"data": f"[음성 자동 선택] 주제 분석 → {_voice_name(channel_voice_id)}\n"}
            elif req.voiceId:
                channel_voice_id = req.voiceId  # 프론트엔드에서 선택한 음성
            if not channel_voice_id:
                channel_preset = get_channel_preset(req.channel)
                if channel_preset:
                    channel_voice_id = channel_preset.get("voice_id")

            yield {"data": f"[생성 엔진] 아트 디렉터({image_label})와 성우(TTS) 동시 작업 중...\n"}

            visual_paths = [None] * len(cuts)
            audio_paths = [None] * len(cuts)
            word_timestamps_list = [None] * len(cuts)
            scripts = [cut["script"] for cut in cuts]

            # 이미지 동시성 제한 — 모듈 레벨 _image_semaphore 사용
            image_semaphore = _image_semaphore

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
                with image_semaphore:
                    try:
                        cut_image_key = _get_image_key()
                        img_path = gen_image_fn(cut["prompt"], i, topic_folder, cut_image_key, model_override=image_model_override, gemini_api_keys=gemini_keys_override, channel=req.channel) if image_engine == "imagen" else gen_image_fn(cut["prompt"], i, topic_folder, cut_image_key, channel=req.channel)
                    except Exception as exc:
                        with errors_lock:
                            errors.append(f"이미지: {exc}")
                        print(f"[컷 {i+1} 이미지 생성 실패] {exc}")

                # 비디오 변환과 TTS를 threading으로 병렬 실행 (데드락 방지: 직접 스레드 사용)
                video_result = [None]  # mutable container for thread result
                tts_result = [None]
                whisper_result = [None]

                def _run_video():
                    try:
                        cut_video_key = get_google_key(llm_key_override, service=active_video_engine, extra_keys=gemini_keys_override)
                        video_result[0] = generate_video_from_image(
                            img_path, cut["prompt"], i, topic_folder, active_video_engine, cut_video_key,
                            description=cut.get("description", ""),
                            veo_model=video_model_override, gemini_api_keys=gemini_keys_override,
                        )
                    except Exception as exc:
                        with errors_lock:
                            errors.append(f"비디오: {exc}")
                        print(f"[컷 {i+1} 비디오 변환 실패] {exc}")

                # 감정 태그 추출 (TTS 감정 매핑용)
                _emotion_match = re.search(r'\[(SHOCK|WONDER|TENSION|REVEAL|CALM)\]', cut.get("description", ""))
                _cut_emotion = _emotion_match.group(1) if _emotion_match else None

                def _run_tts_and_whisper():
                    """TTS 생성 후 바로 Whisper 타임스탬프 추출 (순차 but 동일 스레드)"""
                    try:
                        tts_result[0] = generate_tts(cut["script"], i, topic_folder, elevenlabs_key_override, language=language, speed=req.ttsSpeed, voice_id=channel_voice_id, emotion=_cut_emotion)
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
                            whisper_result[0] = generate_word_timestamps(tts_result[0], api_key_override, language=language)
                        except Exception as exc:
                            with errors_lock:
                                errors.append(f"타임스탬프: {exc}")
                            print(f"[컷 {i+1} 타임스탬프 추출 실패] {exc}")

                threads = []
                # Hero cut 선택: SHOCK/REVEAL 태그만 비디오 생성, 나머지는 Ken Burns (비용 50-70% 절감)
                _hero_emotions = {"SHOCK", "REVEAL"}
                _cut_desc = cut.get("description", "")
                _is_hero = any(f"[{e}]" in _cut_desc for e in _hero_emotions)
                if img_path and active_video_engine != "none" and _is_hero:
                    t = threading.Thread(target=_run_video, name=f"video-cut{i}", daemon=True)
                    t.start()
                    threads.append(t)
                elif img_path and active_video_engine != "none" and not _is_hero:
                    print(f"[컷 {i+1}] 히어로 컷 아님 ({_cut_desc[:30]}…) → Ken Burns 사용")
                t_tts = threading.Thread(target=_run_tts_and_whisper, name=f"tts-cut{i}", daemon=True)
                t_tts.start()
                threads.append(t_tts)

                # 완료 대기 (비디오: 최대 5분, TTS+Whisper: 최대 2분)
                for t in threads:
                    timeout = 480 if "video" in t.name.lower() else 120
                    t.join(timeout=timeout)
                    if t.is_alive():
                        with errors_lock:
                            errors.append(f"타임아웃: {t.name} 스레드가 {timeout}초 내 완료되지 않음")
                        print(f"[컷 {i+1} 타임아웃] {t.name} 스레드가 응답 없음")

                final_visual_path = video_result[0] if video_result[0] else img_path
                words = whisper_result[0] or []
                return i, final_visual_path, tts_result[0], words, errors

            tasks = [loop.run_in_executor(_cut_executor, process_cut, i, cut) for i, cut in enumerate(cuts)]
            completed_count = 0

            all_cut_errors: dict[int, list[str]] = {}

            for future in asyncio.as_completed(tasks):
                i, final_visual_path, aud_path, words, errors = await future
                visual_paths[i] = final_visual_path
                audio_paths[i] = aud_path
                word_timestamps_list[i] = words
                if errors:
                    all_cut_errors[i + 1] = errors

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
                yield {"data": "WARN|[취소됨] 사용자에 의해 생성이 취소되었습니다.\n"}
                return

            yield {"data": "PROG|85\n"}
            platform_label = ", ".join(p.upper() for p in req.platforms)
            yield {"data": f"[렌더링 마스터] Remotion 렌더링 시작 — 플랫폼: {platform_label}\n"}

            # 단계 4: Remotion 비디오 렌더링 (멀티 플랫폼 지원)
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
                _descs = [c.get("description", "") for c in cuts]
                best_img = select_best_thumbnail(visual_paths, descriptions=_descs)
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
                try:
                    _P(abs_output).relative_to(safe_base)
                    path_ok = True
                except ValueError:
                    try:
                        _P(abs_output).relative_to(home_dir)
                        path_ok = True
                    except ValueError:
                        path_ok = False
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

            # Downloads 폴더로 자동 복사 (모든 플랫폼 영상)
            downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            downloads_path = None
            for plat, vpath in video_paths_map.items():
                fname = os.path.basename(vpath)
                if os.path.isdir(downloads_dir):
                    try:
                        dl_path = os.path.join(downloads_dir, fname)
                        await asyncio.to_thread(shutil.copy2, os.path.abspath(vpath), dl_path)
                        if plat == primary_platform:
                            downloads_path = dl_path
                        if len(video_paths_map) > 1:
                            yield {"data": f"[저장] {plat.upper()} 버전 → Downloads/{fname}\n"}
                    except Exception as cp_err:
                        print(f"[Downloads 복사 실패 {plat}] {cp_err}")

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
                yield {"data": f"ERROR|[시스템 오류] {_mask_error(e)}\n"}
          finally:
            # 작업 완료/취소 후 정리
            with _generation_lock:
                if _active_generation_id == generation_id:
                    _active_generation_id = None
                _cancel_events.pop(generation_id, None)

    return EventSourceResponse(sse_generator())


# ── 미리보기 모드: prepare → preview → render ─────────────────────

# 준비된 세션 저장소 (메모리 — 단일 사용자 기준)
_prepared_sessions: dict[str, dict] = {}
_session_lock = threading.Lock()
_SESSION_MAX_AGE = 3600  # 1시간 후 자동 만료
_SESSION_MAX_COUNT = 10  # 최대 세션 수


def _cleanup_sessions():
    """오래된 세션 자동 정리 (메모리 누수 방지)."""
    import time
    now = time.time()
    with _session_lock:
        expired = [sid for sid, s in _prepared_sessions.items() if now - s.get("_created", 0) > _SESSION_MAX_AGE]
        for sid in expired:
            _prepared_sessions.pop(sid, None)
        # 최대 개수 초과 시 가장 오래된 것부터 삭제
        if len(_prepared_sessions) > _SESSION_MAX_COUNT:
            sorted_sessions = sorted(_prepared_sessions.items(), key=lambda x: x[1].get("_created", 0))
            for sid, _ in sorted_sessions[:len(_prepared_sessions) - _SESSION_MAX_COUNT]:
                _prepared_sessions.pop(sid, None)


class PrepareRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    apiKey: str | None = None
    llmProvider: str = "gemini"
    llmKey: str | None = None
    llmModel: str | None = None      # LLM 모델 오버라이드
    imageModel: str | None = None    # 이미지 모델 오버라이드
    geminiKeys: str | None = None  # 프론트엔드 멀티키 (쉼표 구분)
    imageEngine: str = "imagen"
    language: str = "ko"
    videoEngine: str = "none"  # prepare 단계에서는 비디오 미생성이 기본
    channel: str | None = None
    referenceUrl: str | None = None  # YouTube 레퍼런스 URL

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


@app.post("/api/prepare")
async def prepare_endpoint(req: PrepareRequest):
    """1단계: LLM 스크립트 + 이미지 생성만 수행. TTS/렌더는 하지 않음."""

    async def sse_generator():
      async with _generate_semaphore:
        # 프론트엔드 멀티키: 파라미터로 직접 전달 (os.environ 비사용)
        _gemini_keys = req.geminiKeys or None
        try:
            llm_key_for_request = get_google_key(req.llmKey, extra_keys=_gemini_keys) if req.llmProvider == "gemini" else req.llmKey
            loop = asyncio.get_running_loop()

            yield {"data": "PROG|10\n"}
            # YouTube URL 자동 감지
            _yt_pat = re.compile(r"(?:youtube\.com/(?:shorts/|watch\?v=)|youtu\.be/)")
            prep_ref_url = req.referenceUrl
            if not prep_ref_url and _yt_pat.search(req.topic):
                prep_ref_url = req.topic
                yield {"data": "[레퍼런스 분석] YouTube URL 감지 — 영상 분석 후 스타일을 참고합니다\n"}

            yield {"data": f"[기획] '{req.topic}' 스크립트 생성 중...\n"}

            cuts, topic_folder, video_title, video_tags, _seo_desc = await loop.run_in_executor(
                None,
                lambda: generate_cuts(
                    req.topic, api_key_override=req.apiKey, lang=req.language,
                    llm_provider=req.llmProvider, llm_key_override=llm_key_for_request,
                    channel=req.channel, llm_model=req.llmModel,
                    reference_url=prep_ref_url,
                ),
            )

            yield {"data": "PROG|30\n"}
            yield {"data": f"[기획 완료] {len(cuts)}컷 스크립트 생성!\n"}

            # 이미지 생성
            gen_image_fn = generate_image_imagen if req.imageEngine == "imagen" else generate_image_dalle
            image_label = "Imagen 4" if req.imageEngine == "imagen" else "DALL-E"
            yield {"data": f"[이미지] {image_label}로 이미지 생성 중...\n"}

            image_paths = []
            for i, cut in enumerate(cuts):
                try:
                    img_key = get_google_key(req.llmKey, service="imagen", extra_keys=_gemini_keys) if req.imageEngine == "imagen" else req.apiKey
                    _prep_channel = getattr(req, 'channel', None)
                    img_path = await loop.run_in_executor(
                        None, lambda idx=i, c=cut, k=img_key: gen_image_fn(c["prompt"], idx, topic_folder, k) if req.imageEngine != "imagen" else generate_image_imagen(c["prompt"], idx, topic_folder, k, model_override=req.imageModel, gemini_api_keys=_gemini_keys, channel=_prep_channel)
                    )
                    image_paths.append(img_path)
                except Exception as exc:
                    print(f"[컷 {i+1} 이미지 실패] {exc}")
                    image_paths.append(None)

                prog = 30 + int(60 * ((i + 1) / len(cuts)))
                yield {"data": f"PROG|{prog}\n"}
                yield {"data": f"  -> 컷 {i+1}/{len(cuts)} 이미지 생성 완료\n"}

            # 세션 저장 (오래된 세션 자동 정리)
            import uuid as _uuid
            import time as _time
            _cleanup_sessions()
            session_id = _uuid.uuid4().hex[:12]
            with _session_lock:
                _prepared_sessions[session_id] = {
                    "cuts": cuts,
                    "topic_folder": topic_folder,
                    "title": video_title,
                    "image_paths": image_paths,
                    "topic": req.topic,
                    "language": req.language,
                    # API 키는 세션에 저장하지 않음 (보안) — 렌더 요청 시 재전달 필요
                    "_created": _time.time(),
                }

            # 미리보기 데이터 전송
            preview_cuts = []
            for i, cut in enumerate(cuts):
                img_url = None
                if image_paths[i] and os.path.exists(image_paths[i]):
                    rel = image_paths[i].replace("\\", "/")
                    idx = rel.find("assets/")
                    if idx >= 0:
                        img_url = f"/{rel[idx:]}"
                preview_cuts.append({
                    "index": i,
                    "script": cut["script"],
                    "prompt": cut.get("prompt", ""),
                    "description": cut.get("description", ""),
                    "image_url": img_url,
                })

            import json
            yield {"data": "PROG|100\n"}
            yield {"data": f"PREVIEW|{json.dumps({'sessionId': session_id, 'title': video_title, 'cuts': preview_cuts}, ensure_ascii=False)}\n"}

        except Exception as e:
            traceback.print_exc()
            yield {"data": f"ERROR|[준비 오류] {_mask_error(e)}\n"}

    return EventSourceResponse(sse_generator())


class RenderRequest(BaseModel):
    sessionId: str
    cuts: list[dict]  # 수정된 스크립트 포함: [{index, script}, ...]
    apiKey: str | None = None       # 렌더 단계에서 재전달 (세션에 저장하지 않음)
    llmKey: str | None = None       # 렌더 단계에서 재전달
    elevenlabsKey: str | None = None
    ttsSpeed: float = Field(0.9, ge=0.5, le=2.0)
    videoEngine: str = "none"
    cameraStyle: str = "auto"
    bgmTheme: str = "random"
    channel: str | None = None
    platforms: list[str] = ["youtube"]
    captionSize: int = Field(48, ge=32, le=72)
    captionY: int = Field(28, ge=10, le=50)
    outputPath: str | None = None
    voiceId: str | None = None  # ElevenLabs 음성 ID ("auto" → 주제 분석 자동 선택)

    @field_validator("cameraStyle")
    @classmethod
    def valid_camera_style(cls, v: str) -> str:
        allowed = {"auto", "dynamic", "gentle", "static"}
        if v not in allowed:
            raise ValueError(f"지원하지 않는 카메라 스타일: {v}. 허용: {allowed}")
        return v

    @field_validator("platforms")
    @classmethod
    def valid_platforms(cls, v: list[str]) -> list[str]:
        allowed = {"youtube", "tiktok", "reels"}
        for p in v:
            if p not in allowed:
                raise ValueError(f"지원하지 않는 플랫폼: {p}. 허용: {allowed}")
        return v


@app.post("/api/render")
async def render_endpoint(req: RenderRequest):
    """2단계: 수정된 스크립트로 TTS → Whisper → Remotion 렌더링."""
    _cleanup_sessions()
    with _session_lock:
        session = _prepared_sessions.get(req.sessionId)
    if not session:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": "세션이 만료되었습니다. 다시 준비해주세요."})

    async def sse_generator():
        try:
            cuts = copy.deepcopy(session["cuts"])
            topic_folder = session["topic_folder"]
            video_title = session["title"]
            image_paths = session["image_paths"]
            language = session["language"]
            api_key_override = req.apiKey or os.getenv("OPENAI_API_KEY", "")
            elevenlabs_key_override = req.elevenlabsKey or os.getenv("ELEVENLABS_API_KEY", "")

            # 수정된 스크립트 반영
            script_updates = {c["index"]: c["script"] for c in req.cuts if "script" in c}
            for idx, new_script in script_updates.items():
                if 0 <= idx < len(cuts):
                    cuts[idx]["script"] = new_script

            scripts = [cut["script"] for cut in cuts]
            loop = asyncio.get_running_loop()

            # 음성 선택: voiceId(auto/직접) > 채널 설정 > 기본값
            render_voice_id = None
            if req.voiceId == "auto":
                render_voice_id = _auto_select_voice(video_title, language)
            elif req.voiceId:
                render_voice_id = req.voiceId
            if not render_voice_id:
                render_preset = get_channel_preset(req.channel)
                if render_preset:
                    render_voice_id = render_preset.get("voice_id")

            yield {"data": "PROG|10\n"}
            yield {"data": "[음성] TTS 녹음 + 타임스탬프 추출 시작...\n"}

            # TTS + Whisper (순차)
            audio_paths = []
            word_timestamps_list = []
            for i, script in enumerate(scripts):
                try:
                    aud = await loop.run_in_executor(
                        None, lambda idx=i, s=script: generate_tts(s, idx, topic_folder, elevenlabs_key_override, language=language, speed=req.ttsSpeed, voice_id=render_voice_id)
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
            active_video_engine = req.videoEngine
            _hero_emotions = {"SHOCK", "REVEAL"}
            if active_video_engine != "none":
                hero_indices = [i for i, c in enumerate(cuts) if any(f"[{e}]" in c.get("description", "") for e in _hero_emotions)]
                skip_count = len(cuts) - len(hero_indices)
                if skip_count > 0:
                    yield {"data": f"[비디오] 히어로 컷 {len(hero_indices)}개만 비디오 생성 (나머지 {skip_count}개는 Ken Burns)\n"}
                yield {"data": f"[비디오] {active_video_engine} 변환 중...\n"}
                for i, img_path in enumerate(image_paths):
                    if img_path and os.path.exists(img_path) and i in hero_indices:
                        try:
                            llm_key = req.llmKey  # 세션 대신 요청에서 키 수신 (보안)
                            vid_key = get_google_key(llm_key, service=active_video_engine)
                            vid = await loop.run_in_executor(
                                None, lambda idx=i, ip=img_path, p=cuts[idx]["prompt"], vk=vid_key, desc=cuts[idx].get("description", ""): generate_video_from_image(ip, p, idx, topic_folder, active_video_engine, vk, description=desc)
                            )
                            if vid:
                                visual_paths[i] = vid
                        except Exception as exc:
                            print(f"[컷 {i+1} 비디오 변환 실패] {exc}")

            # 실패 체크
            failed = [i+1 for i, p in enumerate(audio_paths) if p is None]
            if failed:
                yield {"data": f"ERROR|[TTS 오류] 컷 {failed} 음성 생성 실패\n"}
                return

            yield {"data": "PROG|70\n"}
            yield {"data": "[렌더링] Remotion 렌더링 시작...\n"}

            # Remotion 렌더
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

            if not render_result:
                yield {"data": "ERROR|[Remotion 오류] 렌더링 실패\n"}
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

            # 세션 정리 (락 보호)
            with _session_lock:
                _prepared_sessions.pop(req.sessionId, None)

        except Exception as e:
            traceback.print_exc()
            yield {"data": f"ERROR|[렌더 오류] {_mask_error(e)}\n"}

    return EventSourceResponse(sse_generator())


# ── BGM 테마 목록 API ──────────────────────────────────────────────

@app.get("/api/bgm-themes")
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


# ── 채널 프리셋 API ──────────────────────────────────────────────

@app.get("/api/channels")
async def list_channels():
    """등록된 채널 목록 및 프리셋 반환."""
    channels = {}
    for name in get_channel_names():
        preset = get_channel_preset(name)
        if preset:
            # voice_id는 내부용이므로 프론트엔드에 노출하지 않음
            channels[name] = {k: v for k, v in preset.items() if k != "voice_id"}
    return {"channels": channels}


# ── YouTube 업로드 API ─────────────────────────────────────────────

# AI 공시 문구 (EU AI Act 2024/1689 + YouTube/TikTok 정책 준수)
_AI_DISCLOSURE_SUFFIX = "\n\n🤖 This video uses AI-generated visuals and narration."
_AI_DISCLOSURE_SUFFIX_KO = "\n\n🤖 이 영상은 AI 생성 이미지와 내레이션을 사용합니다."


class YouTubeUploadRequest(BaseModel):
    video_path: str = Field(..., description="업로드할 동영상 경로")
    title: str = Field(..., max_length=100)
    description: str = Field("", max_length=5000)
    tags: list[str] = Field(default_factory=list)
    privacy: str = Field("private", pattern="^(private|unlisted|public)$")
    channel_id: str | None = None
    publish_at: str | None = Field(None, description="예약 공개 시간 (ISO 8601, e.g. 2026-03-20T15:00:00Z)")
    ai_disclosure: bool = Field(True, description="AI 생성 콘텐츠 공시 자동 추가")


@app.get("/api/youtube/status")
async def youtube_status():
    from modules.upload.youtube import get_auth_status
    return get_auth_status()


@app.post("/api/youtube/auth")
async def youtube_auth():
    from modules.upload.youtube import create_auth_url
    try:
        url = create_auth_url()
        return {"auth_url": url}
    except FileNotFoundError as e:
        return {"error": str(e)}


@app.get("/api/youtube/callback")
async def youtube_callback(code: str, state: str | None = None):
    from modules.upload.youtube import handle_auth_callback
    from fastapi.responses import HTMLResponse
    try:
        result = handle_auth_callback(code, state)
        return HTMLResponse(
            "<html><body><h2>YouTube 연동 완료!</h2>"
            "<p>이 창을 닫고 돌아가세요.</p>"
            "<script>window.close()</script></body></html>"
        )
    except Exception as e:
        import html as _html
        return HTMLResponse(f"<html><body><h2>오류</h2><p>{_html.escape(str(e))}</p></body></html>", status_code=400)


@app.post("/api/youtube/upload")
async def youtube_upload(req: YouTubeUploadRequest):
    from modules.upload.youtube import upload_video
    try:
        # 경로 보안 검증
        from pathlib import Path as _P
        abs_path = os.path.abspath(os.path.realpath(req.video_path))
        assets_dir = os.path.abspath(os.path.realpath("assets"))
        if not _P(abs_path).is_relative_to(assets_dir):
            return {"error": "assets 디렉토리 내의 파일만 업로드할 수 있습니다."}

        # AI 공시 자동 추가 (EU AI Act + YouTube 정책)
        upload_desc = req.description
        if req.ai_disclosure and _AI_DISCLOSURE_SUFFIX_KO not in upload_desc and _AI_DISCLOSURE_SUFFIX not in upload_desc:
            upload_desc += _AI_DISCLOSURE_SUFFIX_KO

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _cut_executor,
            lambda: upload_video(
                video_path=abs_path,
                title=req.title,
                description=upload_desc,
                tags=req.tags,
                privacy=req.privacy,
                channel_id=req.channel_id,
                publish_at=req.publish_at,
            )
        )
        return result
    except PermissionError as e:
        return {"error": _mask_error(e), "need_auth": True}
    except (FileNotFoundError, ValueError) as e:
        return {"error": _mask_error(e)}
    except Exception as e:
        return {"error": f"업로드 실패: {_mask_error(e)}"}


@app.post("/api/youtube/disconnect")
async def youtube_disconnect():
    from modules.upload.youtube import disconnect
    return disconnect()


# ── TikTok 업로드 API ─────────────────────────────────────────────

class TikTokUploadRequest(BaseModel):
    video_path: str = Field(..., description="업로드할 동영상 경로")
    title: str = Field(..., max_length=150)
    privacy_level: str = Field("SELF_ONLY", pattern="^(SELF_ONLY|MUTUAL_FOLLOW_FRIENDS|FOLLOWER_OF_CREATOR|PUBLIC_TO_EVERYONE)$")
    user_id: str | None = None
    schedule_time: int | None = Field(None, description="예약 발행 UTC Unix timestamp (15분~75일 이내)")
    ai_disclosure: bool = Field(True, description="AI 생성 콘텐츠 공시 (TikTok AIGC 정책)")


@app.get("/api/tiktok/status")
async def tiktok_status():
    from modules.upload.tiktok import get_auth_status
    return get_auth_status()


@app.post("/api/tiktok/auth")
async def tiktok_auth():
    from modules.upload.tiktok import create_auth_url
    try:
        url = create_auth_url()
        return {"auth_url": url}
    except ValueError as e:
        return {"error": str(e)}


@app.get("/api/tiktok/callback")
async def tiktok_callback(code: str, state: str | None = None):
    from modules.upload.tiktok import handle_auth_callback
    from fastapi.responses import HTMLResponse
    try:
        handle_auth_callback(code, state=state)
        return HTMLResponse(
            "<html><body><h2>TikTok 연동 완료!</h2>"
            "<p>이 창을 닫고 돌아가세요.</p>"
            "<script>window.close()</script></body></html>"
        )
    except Exception as e:
        import html as _html
        return HTMLResponse(f"<html><body><h2>오류</h2><p>{_html.escape(str(e))}</p></body></html>", status_code=400)


@app.post("/api/tiktok/upload")
async def tiktok_upload(req: TikTokUploadRequest):
    from modules.upload.tiktok import upload_video
    try:
        from pathlib import Path as _P
        abs_path = os.path.abspath(os.path.realpath(req.video_path))
        assets_dir = os.path.abspath(os.path.realpath("assets"))
        if not _P(abs_path).is_relative_to(assets_dir):
            return {"error": "assets 디렉토리 내의 파일만 업로드할 수 있습니다."}

        # AI 공시 자동 추가 (TikTok AIGC 정책 — 2026 Q1 230만 건 삭제)
        upload_title = req.title
        if req.ai_disclosure and "[AI Generated]" not in upload_title:
            upload_title = upload_title.rstrip() + " #AI생성"

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _cut_executor,
            lambda: upload_video(
                video_path=abs_path,
                title=upload_title,
                privacy_level=req.privacy_level,
                user_id=req.user_id,
                schedule_time=req.schedule_time,
            )
        )
        return result
    except PermissionError as e:
        return {"error": _mask_error(e), "need_auth": True}
    except (FileNotFoundError, ValueError) as e:
        return {"error": _mask_error(e)}
    except Exception as e:
        return {"error": f"업로드 실패: {_mask_error(e)}"}


@app.post("/api/tiktok/disconnect")
async def tiktok_disconnect():
    from modules.upload.tiktok import disconnect
    return disconnect()


# ── Instagram Reels 업로드 API ────────────────────────────────────

class InstagramUploadRequest(BaseModel):
    video_path: str = Field(..., description="업로드할 동영상 경로")
    caption: str = Field("", max_length=2200)
    account_id: str | None = None
    video_url: str | None = Field(None, description="공개 접근 가능한 영상 URL (로컬 파일 대신)")


@app.get("/api/instagram/status")
async def instagram_status():
    from modules.upload.instagram import get_auth_status
    return get_auth_status()


@app.post("/api/instagram/auth")
async def instagram_auth():
    from modules.upload.instagram import create_auth_url
    try:
        url = create_auth_url()
        return {"auth_url": url}
    except ValueError as e:
        return {"error": str(e)}


@app.get("/api/instagram/callback")
async def instagram_callback(code: str, state: str | None = None):
    from modules.upload.instagram import handle_auth_callback
    from fastapi.responses import HTMLResponse
    try:
        handle_auth_callback(code, state=state)
        return HTMLResponse(
            "<html><body><h2>Instagram 연동 완료!</h2>"
            "<p>이 창을 닫고 돌아가세요.</p>"
            "<script>window.close()</script></body></html>"
        )
    except Exception as e:
        import html as _html
        return HTMLResponse(f"<html><body><h2>오류</h2><p>{_html.escape(str(e))}</p></body></html>", status_code=400)


@app.post("/api/instagram/upload")
async def instagram_upload(req: InstagramUploadRequest):
    from modules.upload.instagram import upload_reels
    try:
        from pathlib import Path as _P
        abs_path = os.path.abspath(os.path.realpath(req.video_path))
        assets_dir = os.path.abspath(os.path.realpath("assets"))
        if not _P(abs_path).is_relative_to(assets_dir):
            return {"error": "assets 디렉토리 내의 파일만 업로드할 수 있습니다."}

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            _cut_executor,
            lambda: upload_reels(
                video_path=abs_path,
                caption=req.caption,
                account_id=req.account_id,
                video_url=req.video_url,
            )
        )
        return result
    except PermissionError as e:
        return {"error": _mask_error(e), "need_auth": True}
    except (FileNotFoundError, ValueError) as e:
        return {"error": _mask_error(e)}
    except Exception as e:
        return {"error": f"업로드 실패: {_mask_error(e)}"}


@app.post("/api/instagram/disconnect")
async def instagram_disconnect():
    from modules.upload.instagram import disconnect
    return disconnect()


# ── 다국어 생성 API ─────────────────────────────────────────────
# 이미지/비디오는 공유, TTS+자막+메타데이터만 언어별 생성 (비용 ~60% 절감)

class MultiLangRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    languages: list[str] = Field(..., min_length=1, max_length=5, description="생성할 언어 목록 (예: ['ko', 'en', 'es'])")
    apiKey: str | None = None
    elevenlabsKey: str | None = None
    videoEngine: str = "none"
    imageEngine: str = "imagen"
    llmProvider: str = "gemini"
    llmModel: str | None = None
    geminiKeys: str | None = None
    cameraStyle: str = "auto"
    bgmTheme: str = "random"
    channel: str | None = None
    platforms: list[str] = ["youtube"]
    ttsSpeed: float = Field(0.9, ge=0.5, le=2.0)
    voiceId: str | None = None
    captionSize: int = Field(48, ge=32, le=72)
    captionY: int = Field(28, ge=10, le=50)
    mode: str = "production"

    @field_validator("languages")
    @classmethod
    def valid_languages(cls, v: list[str]) -> list[str]:
        allowed = {"ko", "en", "de", "da", "no", "es", "fr", "pt", "it", "nl", "sv", "pl", "ru", "ja", "zh", "ar", "tr", "hi"}
        for lang in v:
            if lang not in allowed:
                raise ValueError(f"지원하지 않는 언어: {lang}")
        return list(dict.fromkeys(v))  # deduplicate preserving order

    @field_validator("cameraStyle")
    @classmethod
    def valid_camera_style(cls, v: str) -> str:
        allowed = {"auto", "dynamic", "gentle", "static"}
        if v not in allowed:
            raise ValueError(f"지원하지 않는 카메라 스타일: {v}. 허용: {allowed}")
        return v

    @field_validator("platforms")
    @classmethod
    def valid_platforms(cls, v: list[str]) -> list[str]:
        allowed = {"youtube", "tiktok", "reels"}
        for p in v:
            if p not in allowed:
                raise ValueError(f"지원하지 않는 플랫폼: {p}. 허용: {allowed}")
        return v


@app.post("/api/generate-multilang")
async def generate_multilang(req: MultiLangRequest):
    """다국어 영상 생성 (SSE): 이미지/비디오 1회 공유, 언어별 TTS+자막+렌더.
    3언어 × 3플랫폼 = 9개 업로드 가능한 3개 영상을 생성합니다."""

    api_key_override = req.apiKey
    elevenlabs_key_override = req.elevenlabsKey
    llm_provider = req.llmProvider
    llm_key_override = None
    gemini_keys_override = req.geminiKeys
    languages = req.languages
    primary_lang = languages[0]

    async def multilang_sse():
        async with _generate_semaphore:
          try:
            loop = asyncio.get_running_loop()
            total_langs = len(languages)
            yield {"data": f"[다국어 생성] {total_langs}개 언어 영상 생성 시작: {', '.join(languages)}\n"}
            yield {"data": f"[비용 최적화] 이미지/비디오 1회 생성 → TTS+자막만 {total_langs}회 = ~{int((total_langs-1)/total_langs*100)}% 절감\n"}

            # ── 단계 1: 첫 번째 언어로 LLM 기획 ────────────────────
            yield {"data": f"PROG|5\n"}
            yield {"data": f"[기획] '{req.topic}' 기획 시작 ({primary_lang.upper()})...\n"}

            llm_key_for_request = get_google_key(llm_key_override, extra_keys=gemini_keys_override) if llm_provider == "gemini" else llm_key_override
            cuts, topic_folder, video_title, video_tags, video_seo_desc = await loop.run_in_executor(
                None,
                lambda: generate_cuts(
                    req.topic, api_key_override=api_key_override,
                    lang=primary_lang, llm_provider=llm_provider,
                    llm_key_override=llm_key_for_request,
                    channel=req.channel, llm_model=req.llmModel,
                ),
            )
            yield {"data": f"PROG|15\n"}
            yield {"data": f"[기획 완료] 총 {len(cuts)}컷 기획 완료!\n"}

            # ── 단계 2: 이미지 생성 (1회, 전 언어 공유) ──────────
            yield {"data": f"[이미지 생성] {len(cuts)}컷 이미지 생성 시작 (전 언어 공유)...\n"}

            image_engine = req.imageEngine
            visual_paths = [None] * len(cuts)
            descriptions = [cut.get("description", "") for cut in cuts]

            # 이미지 생성 (기존 파이프라인 로직 활용)
            gen_image_fn = generate_image_imagen if image_engine == "imagen" else generate_image_dalle
            for i, cut in enumerate(cuts):
                try:
                    cut_image_key = get_google_key(api_key_override, service="imagen", extra_keys=gemini_keys_override) if image_engine == "imagen" else api_key_override
                    with _image_semaphore:
                        if image_engine == "imagen":
                            img_path = await loop.run_in_executor(_cut_executor, lambda idx=i, c=cut: gen_image_fn(c["prompt"], idx, topic_folder, cut_image_key, model_override=None, gemini_api_keys=gemini_keys_override, channel=req.channel))
                        else:
                            img_path = await loop.run_in_executor(_cut_executor, lambda idx=i, c=cut: gen_image_fn(c["prompt"], idx, topic_folder, cut_image_key, channel=req.channel))
                    visual_paths[i] = img_path
                except Exception as img_err:
                    print(f"[다국어 이미지 오류] 컷 {i+1}: {img_err}")

                prog = 15 + int(25 * ((i + 1) / len(cuts)))
                yield {"data": f"PROG|{prog}\n"}

            yield {"data": f"[이미지 완료] {sum(1 for p in visual_paths if p)}개 이미지 생성 성공\n"}

            # ── 단계 3: 히어로 컷 비디오 생성 (1회, 전 언어 공유) ──
            active_video_engine = req.videoEngine
            is_draft = req.mode == "draft"
            if is_draft:
                active_video_engine = "none"

            _hero_emotions = {"SHOCK", "REVEAL"}
            hero_video_paths = {}  # index → video_path

            if active_video_engine != "none":
                hero_cuts = [(i, cut) for i, cut in enumerate(cuts) if any(f"[{e}]" in cut.get("description", "") for e in _hero_emotions)]
                yield {"data": f"[비디오 생성] 히어로 컷 {len(hero_cuts)}개 비디오 렌더링 시작...\n"}

                for i, cut in hero_cuts:
                    if visual_paths[i]:
                        try:
                            vid_key = get_google_key(api_key_override, service="veo3", extra_keys=gemini_keys_override) if active_video_engine == "veo3" else api_key_override
                            vid_path = await loop.run_in_executor(
                                _cut_executor,
                                lambda idx=i, c=cut, img=visual_paths[i]: generate_video_from_image(
                                    img, c["prompt"], idx, topic_folder,
                                    engine=active_video_engine,
                                    google_api_key=vid_key,
                                    description=c.get("description", ""),
                                    gemini_api_keys=gemini_keys_override,
                                ),
                            )
                            if vid_path:
                                hero_video_paths[i] = vid_path
                                visual_paths[i] = vid_path
                        except Exception as vid_err:
                            print(f"[다국어 비디오 오류] 컷 {i+1}: {vid_err}")

                yield {"data": f"[비디오 완료] {len(hero_video_paths)}개 히어로 비디오 생성 성공\n"}

            yield {"data": f"PROG|45\n"}

            # ── 단계 4: 언어별 TTS + 자막 + 렌더 ─────────────────
            all_results = {}  # lang → {"video_path": ..., "title": ..., "tags": [...]}

            for lang_idx, lang in enumerate(languages):
                lang_upper = lang.upper()
                base_prog = 45 + int(50 * (lang_idx / total_langs))
                yield {"data": f"PROG|{base_prog}\n"}
                yield {"data": f"[{lang_upper}] === 언어 {lang_idx+1}/{total_langs}: {lang_upper} 생성 시작 ===\n"}

                # 첫 언어가 아니면 해당 언어로 대본 재생성
                if lang_idx > 0:
                    yield {"data": f"[{lang_upper}] LLM 대본 재생성 중...\n"}
                    try:
                        llm_key_for_lang = get_google_key(llm_key_override, extra_keys=gemini_keys_override) if llm_provider == "gemini" else llm_key_override
                        lang_cuts, _, lang_title, lang_tags, lang_seo = await loop.run_in_executor(
                            None,
                            lambda l=lang: generate_cuts(
                                req.topic, api_key_override=api_key_override,
                                lang=l, llm_provider=llm_provider,
                                llm_key_override=llm_key_for_lang,
                                channel=req.channel, llm_model=req.llmModel,
                            ),
                        )
                    except Exception as llm_err:
                        yield {"data": f"WARN|[{lang_upper}] 대본 생성 실패: {llm_err}\n"}
                        continue
                else:
                    lang_cuts = cuts
                    lang_title = video_title
                    lang_tags = video_tags
                    lang_seo = video_seo_desc

                # 컷 수를 공유 이미지 수에 맞춤 (2차 언어 LLM이 다른 수를 생성할 수 있음)
                n_shared = len(visual_paths)
                if len(lang_cuts) > n_shared:
                    lang_cuts = lang_cuts[:n_shared]
                elif len(lang_cuts) < n_shared:
                    # 부족한 컷은 마지막 컷을 복사 (이미지는 있지만 대본이 없으면 무음)
                    while len(lang_cuts) < n_shared:
                        lang_cuts.append(dict(lang_cuts[-1]) if lang_cuts else {"script": "...", "description": "", "prompt": ""})

                # 언어별 TTS 생성
                yield {"data": f"[{lang_upper}] TTS 음성 생성 중 ({len(lang_cuts)}컷)...\n"}
                lang_audio_paths = [None] * len(lang_cuts)
                lang_word_timestamps = [[] for _ in lang_cuts]
                lang_scripts = [c.get("script", "") for c in lang_cuts]

                # 언어별 topic_folder 생성 (같은 이미지, 다른 오디오)
                lang_topic_folder = f"{topic_folder}_{lang}"
                lang_audio_dir = os.path.join("assets", lang_topic_folder, "audio")
                os.makedirs(lang_audio_dir, exist_ok=True)

                for i, cut in enumerate(lang_cuts):
                    try:
                        _emotion_match = re.search(r'\[(SHOCK|WONDER|TENSION|REVEAL|CALM)\]', cut.get("description", ""))
                        _cut_emotion = _emotion_match.group(1) if _emotion_match else None

                        aud_path = await loop.run_in_executor(
                            _cut_executor,
                            lambda idx=i, c=cut: generate_tts(
                                c.get("script", ""), idx, lang_topic_folder,
                                elevenlabs_key_override, language=lang,
                                speed=req.ttsSpeed, voice_id=req.voiceId,
                                emotion=_cut_emotion,
                            ),
                        )
                        if aud_path:
                            try:
                                aud_path = normalize_audio_lufs(aud_path)
                            except Exception:
                                pass
                            lang_audio_paths[i] = aud_path

                            # Whisper 타임스탬프
                            try:
                                words = await loop.run_in_executor(
                                    _cut_executor,
                                    lambda ap=aud_path: generate_word_timestamps(ap, api_key_override, language=lang),
                                )
                                lang_word_timestamps[i] = words or []
                            except Exception:
                                pass
                    except Exception as tts_err:
                        print(f"[{lang_upper} TTS 오류] 컷 {i+1}: {tts_err}")

                tts_prog = base_prog + int(30 / total_langs)
                yield {"data": f"PROG|{tts_prog}\n"}
                yield {"data": f"[{lang_upper}] TTS 완료: {sum(1 for p in lang_audio_paths if p)}/{len(lang_cuts)}컷\n"}

                # 언어별 Remotion 렌더링 (공유 이미지 + 언어별 오디오)
                yield {"data": f"[{lang_upper}] Remotion 렌더링 시작...\n"}
                try:
                    render_result = await loop.run_in_executor(
                        None,
                        lambda: create_remotion_video(
                            visual_paths[:len(lang_cuts)], lang_audio_paths, lang_scripts,
                            lang_word_timestamps, lang_topic_folder,
                            title=lang_title,
                            camera_style=req.cameraStyle,
                            bgm_theme=req.bgmTheme,
                            channel=req.channel,
                            platforms=None,  # 통합 렌더 (인트로 없음, 아웃트로만)
                            caption_size=req.captionSize,
                            caption_y=req.captionY,
                            descriptions=descriptions[:len(lang_cuts)],
                        ),
                    )
                    if render_result:
                        vid_path = render_result if isinstance(render_result, str) else list(render_result.values())[0]
                        all_results[lang] = {
                            "video_path": f"/assets/{lang_topic_folder}/video/{os.path.basename(vid_path)}",
                            "abs_path": os.path.abspath(vid_path),
                            "title": lang_title,
                            "tags": lang_tags,
                            "seo_description": lang_seo,
                        }

                        # Downloads 폴더에 복사
                        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
                        if os.path.isdir(downloads_dir):
                            try:
                                dl_name = f"{lang_topic_folder}_{lang_upper}.mp4"
                                dl_path = os.path.join(downloads_dir, dl_name)
                                await asyncio.to_thread(shutil.copy2, os.path.abspath(vid_path), dl_path)
                                yield {"data": f"[{lang_upper}] 📂 Downloads/{dl_name} 저장 완료\n"}
                            except Exception:
                                pass

                        yield {"data": f"[{lang_upper}] ✅ 렌더링 완료!\n"}
                    else:
                        yield {"data": f"WARN|[{lang_upper}] 렌더링 실패\n"}
                except Exception as render_err:
                    yield {"data": f"WARN|[{lang_upper}] 렌더링 오류: {_mask_error(render_err)}\n"}

            # ── 단계 5: 최종 결과 ──────────────────────────────────
            yield {"data": "PROG|100\n"}
            completed = list(all_results.keys())
            yield {"data": f"[완료] 다국어 생성 완료: {', '.join(l.upper() for l in completed)} ({len(completed)}/{total_langs}개)\n"}

            # 결과 JSON 전송
            import json
            result_data = {
                "type": "multilang_complete",
                "languages": completed,
                "videos": {lang: info["video_path"] for lang, info in all_results.items()},
                "titles": {lang: info["title"] for lang, info in all_results.items()},
                "tags": {lang: info["tags"] for lang, info in all_results.items()},
            }
            yield {"data": f"RESULT|{json.dumps(result_data, ensure_ascii=False)}\n"}
            yield {"data": f"DONE|{all_results[completed[0]]['video_path'] if completed else ''}\n"}

          except Exception as e:
            traceback.print_exc()
            yield {"data": f"ERROR|[다국어 생성 오류] {_mask_error(e)}\n"}

    return EventSourceResponse(multilang_sse())


# ── 배치 생성 큐 API ──────────────────────────────────────────────

class BatchJobRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    language: str = "ko"
    cameraStyle: str = "auto"
    bgmTheme: str = "random"
    llmProvider: str = "gemini"
    videoEngine: str = "none"
    imageEngine: str = "imagen"
    channel: str | None = None

    @field_validator("language")
    @classmethod
    def valid_language(cls, v: str) -> str:
        allowed = {"ko", "en", "de", "da", "no", "es", "fr", "pt", "it", "nl", "sv", "pl", "ru", "ja", "zh", "ar", "tr", "hi"}
        if v not in allowed:
            raise ValueError(f"지원하지 않는 언어: {v}")
        return v

    @field_validator("videoEngine")
    @classmethod
    def valid_engine(cls, v: str) -> str:
        if v not in {"kling", "sora2", "veo3", "none"}:
            raise ValueError(f"지원하지 않는 비디오 엔진: {v}")
        return v

    @field_validator("imageEngine")
    @classmethod
    def valid_image_engine(cls, v: str) -> str:
        if v not in {"dalle", "imagen"}:
            raise ValueError(f"지원하지 않는 이미지 엔진: {v}")
        return v

    @field_validator("llmProvider")
    @classmethod
    def valid_llm_provider(cls, v: str) -> str:
        if v not in {"openai", "gemini", "claude"}:
            raise ValueError(f"지원하지 않는 LLM 프로바이더: {v}")
        return v

    @field_validator("cameraStyle")
    @classmethod
    def valid_camera_style(cls, v: str) -> str:
        allowed = {"auto", "dynamic", "gentle", "static"}
        if v not in allowed:
            raise ValueError(f"지원하지 않는 카메라 스타일: {v}. 허용: {allowed}")
        return v

class BatchBulkRequest(BaseModel):
    jobs: list[BatchJobRequest] = Field(..., max_length=50)  # 큐 폭주 방지

_batch_running = False
_batch_lock = threading.Lock()
_batch_stop = threading.Event()

@app.post("/api/batch/add")
async def batch_add(req: BatchJobRequest):
    from modules.utils.batch import add_job
    job_id = add_job(req.topic, req.language, req.cameraStyle, req.bgmTheme, req.llmProvider, req.videoEngine, req.imageEngine, req.channel)
    return {"id": job_id, "message": f"작업 #{job_id} 큐에 추가됨"}

@app.post("/api/batch/add-bulk")
async def batch_add_bulk(req: BatchBulkRequest):
    from modules.utils.batch import add_jobs_bulk
    topics = [j.model_dump() for j in req.jobs]
    ids = add_jobs_bulk(topics)
    return {"ids": ids, "message": f"{len(ids)}개 작업 큐에 추가됨"}

@app.get("/api/batch/queue")
async def batch_queue():
    from modules.utils.batch import get_queue, get_stats
    return {"jobs": get_queue(), "stats": get_stats()}

@app.get("/api/batch/stats")
async def batch_stats():
    from modules.utils.batch import get_stats
    return get_stats()

@app.post("/api/batch/start")
async def batch_start():
    """배치 큐의 대기 작업을 순차 실행합니다."""
    global _batch_running
    with _batch_lock:
        if _batch_running:
            return {"message": "배치가 이미 실행 중입니다", "running": True}
        _batch_stop.clear()
        _batch_running = True

    async def _run_batch():
        global _batch_running
        from modules.utils.batch import get_next_pending, update_job
        from datetime import datetime
        loop = asyncio.get_running_loop()
        try:
            while not _batch_stop.is_set():
                job = get_next_pending()
                if not job:
                    print("[배치] 대기 작업 없음 — 배치 완료")
                    break
                job_id = job["id"]
                print(f"[배치] 작업 #{job_id} 시작: {job['topic']}")
                update_job(job_id, status="running", started_at=datetime.now().isoformat())

                try:
                    # 기획 (Gemini 키 로테이션 재시도 — 메인 생성과 동일 패턴)
                    cuts, topic_folder, title = None, None, None
                    _excluded = set()
                    for _attempt in range(max(count_google_keys(), 1)):
                        llm_key = get_google_key(None, service="gemini", exclude=_excluded) if job["llm_provider"] == "gemini" else None
                        try:
                            cuts, topic_folder, title, _tags, _seo = await loop.run_in_executor(
                                None, lambda k=llm_key: generate_cuts(job["topic"], lang=job["language"], llm_provider=job["llm_provider"], llm_key_override=k)
                            )
                            break
                        except Exception as _e:
                            if "429" in str(_e) and llm_key:
                                from modules.utils.keys import mark_key_exhausted
                                mark_key_exhausted(llm_key, "gemini")
                                _excluded.add(llm_key)
                                print(f"[배치] 작업 #{job_id} Gemini 키 재시도 ({_attempt+1})")
                                continue
                            raise
                    if cuts is None:
                        raise RuntimeError("기획 생성 실패 — 모든 키 소진")

                    # 이미지 + TTS + Whisper (순차)
                    visual_paths, audio_paths, scripts, word_ts_list = [], [], [], []
                    for i, cut in enumerate(cuts):
                        if job["image_engine"] == "imagen":
                            _batch_channel = job.get("channel")
                            img = await loop.run_in_executor(None, lambda idx=i, c=cut: generate_image_imagen(c["prompt"], idx, topic_folder, channel=_batch_channel))
                        else:
                            _batch_ch = job.get("channel")
                            img = await loop.run_in_executor(None, lambda idx=i, c=cut: generate_image_dalle(c["prompt"], idx, topic_folder, channel=_batch_ch))
                        visual_paths.append(img)

                        aud = await loop.run_in_executor(None, lambda idx=i, c=cut: generate_tts(c["script"], idx, topic_folder, language=job["language"]))
                        if aud:
                            aud = normalize_audio_lufs(aud)
                        audio_paths.append(aud)

                        words = []
                        if aud:
                            words = await loop.run_in_executor(None, lambda a=aud: generate_word_timestamps(a, language=job["language"]))
                        word_ts_list.append(words)
                        scripts.append(cut["script"])

                    # 렌더링
                    video_path = await loop.run_in_executor(
                        None, lambda: create_remotion_video(
                            visual_paths, audio_paths, scripts, word_ts_list, topic_folder,
                            title=title, camera_style=job["camera_style"], bgm_theme=job["bgm_theme"],
                            channel=job.get("channel"),
                            descriptions=[c.get("description", "") for c in cuts],
                        )
                    )

                    if video_path:
                        update_job(job_id, status="completed", video_path=video_path, completed_at=datetime.now().isoformat())
                        print(f"OK [배치] 작업 #{job_id} 완료: {video_path}")
                    else:
                        update_job(job_id, status="failed", error="Remotion 렌더링 실패", completed_at=datetime.now().isoformat())

                except Exception as e:
                    from datetime import datetime as _dt
                    _err_msg = _mask_error(e)
                    update_job(job_id, status="failed", error=_err_msg, completed_at=_dt.now().isoformat())
                    print(f"[배치 오류] 작업 #{job_id}: {_err_msg}")

        finally:
            with _batch_lock:
                _batch_running = False
            print("[배치] 배치 프로세스 종료")

    asyncio.create_task(_run_batch())
    return {"message": "배치 실행 시작", "running": True}

@app.post("/api/batch/stop")
async def batch_stop():
    global _batch_running
    _batch_stop.set()
    return {"message": "배치 중지 요청됨 (현재 작업 완료 후 중지)", "running": _batch_running}

@app.delete("/api/batch/job/{job_id}")
async def batch_delete(job_id: int):
    from modules.utils.batch import delete_job
    ok = delete_job(job_id)
    return {"success": ok, "message": f"작업 #{job_id} {'삭제됨' if ok else '삭제 불가 (실행 중이거나 존재하지 않음)'}"}

@app.post("/api/batch/clear")
async def batch_clear():
    from modules.utils.batch import clear_completed
    count = clear_completed()
    return {"cleared": count, "message": f"완료/실패 작업 {count}건 정리됨"}


# ── 플랫폼 통합 상태 API ─────────────────────────────────────────

@app.get("/api/upload/platforms")
async def upload_platforms():
    """모든 업로드 플랫폼의 연동 상태를 한번에 반환합니다."""
    from modules.upload.youtube import get_auth_status as yt_status
    from modules.upload.tiktok import get_auth_status as tt_status
    from modules.upload.instagram import get_auth_status as ig_status
    return {
        "youtube": yt_status(),
        "tiktok": tt_status(),
        "instagram": ig_status(),
    }


# ── Legal pages (TikTok/Instagram 앱 등록용) ─────────────────────

@app.get("/terms", response_class=HTMLResponse)
async def terms_of_service():
    legal_path = os.path.join(os.path.dirname(__file__), "legal", "terms.html")
    with open(legal_path, "r", encoding="utf-8") as f:
        return f.read()

@app.get("/privacy", response_class=HTMLResponse)
async def privacy_policy():
    legal_path = os.path.join(os.path.dirname(__file__), "legal", "privacy.html")
    with open(legal_path, "r", encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("API_PORT", "8003"))
    reload = os.getenv("UVICORN_RELOAD", "true").lower() == "true"
    uvicorn.run("api_server:app", host="0.0.0.0", port=port, reload=reload)
