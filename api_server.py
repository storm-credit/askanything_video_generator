import os
import sys
import io
import shutil
import asyncio
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI
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
from modules.utils.keys import get_google_key, count_google_keys, count_available_keys, get_key_usage_stats

app = FastAPI()

# 동시 생성 요청 제한 (GPU/API 과부하 방지)
_generate_semaphore = asyncio.Semaphore(int(os.getenv("MAX_CONCURRENT_GENERATE", "2")))
# 컷 병렬 처리용 공유 스레드풀 (요청마다 생성/삭제 방지)
_cut_executor = ThreadPoolExecutor(max_workers=4)


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
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    apiKey: str | None = None
    elevenlabsKey: str | None = None
    videoEngine: str = "veo3"
    imageEngine: str = "imagen"
    llmProvider: str = "gemini"
    llmKey: str | None = None
    outputPath: str | None = None
    language: str = "ko"

    @field_validator("language")
    @classmethod
    def valid_language(cls, v: str) -> str:
        allowed = {"ko", "en"}
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
        allowed = {"kling", "sora2", "veo3", "hailuo", "wan", "none"}
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
    claude_key = os.getenv("ANTHROPIC_API_KEY", "")
    hf_key = os.getenv("HIGGSFIELD_API_KEY", "")
    hf_id = os.getenv("HIGGSFIELD_ACCOUNT_ID", "")
    kling_ak = os.getenv("KLING_ACCESS_KEY", "")
    kling_sk = os.getenv("KLING_SECRET_KEY", "")

    keys = {
        "openai": _is_set(openai_key, ["sk-proj-YOUR"]),
        "elevenlabs": _is_set(elevenlabs_key, ["YOUR_ELEVENLABS_API_KEY_HERE"]),
        "gemini": _is_set(gemini_key),
        "claude_key": _is_set(claude_key),
        "higgsfield_key": _is_set(hf_key, ["YOUR"]),
        "higgsfield_account": _is_set(hf_id, ["YOUR"]),
        "kling_access": _is_set(kling_ak, ["YOUR"]),
        "kling_secret": _is_set(kling_sk, ["YOUR"]),
    }

    missing = [k for k, v in keys.items() if not v]
    google_key_count = count_google_keys()
    return {
        "status": "ok" if not missing else "missing_keys",
        "keys": keys,
        "missing": missing,
        "google_key_count": google_key_count,
    }


def _validate_keys(api_key_override: str | None, elevenlabs_key_override: str | None, video_engine: str,
                    image_engine: str = "imagen", llm_provider: str = "gemini", llm_key_override: str | None = None) -> list[str]:
    """파이프라인 시작 전 필수 키 검증. 누락된 키 이름 목록을 반환."""
    errors = []

    # OpenAI 키: DALL-E 사용 시 또는 Whisper 자막에 필요
    openai_key = api_key_override or os.getenv("OPENAI_API_KEY", "")
    openai_needed_for = []
    if image_engine == "dalle":
        openai_needed_for.append("DALL-E 이미지")
    openai_needed_for.append("Whisper 자막")
    if llm_provider == "openai":
        openai_needed_for.insert(0, "GPT 기획")

    if (image_engine == "dalle" or llm_provider == "openai") and (not openai_key or openai_key.startswith("sk-proj-YOUR")):
        errors.append(f"OPENAI_API_KEY ({' + '.join(openai_needed_for)}에 필수)")
    elif not openai_key or openai_key.startswith("sk-proj-YOUR"):
        # Whisper만 필요 - 경고 수준 (나중에 WARN으로 처리 가능)
        errors.append("OPENAI_API_KEY (Whisper 자막 타임스탬프에 필수)")

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

    # Kling: 직접 API 또는 Higgsfield
    if video_engine == "kling":
        kling_ak = os.getenv("KLING_ACCESS_KEY", "")
        if not kling_ak or kling_ak.startswith("YOUR"):
            errors.append("KLING_ACCESS_KEY (Kling 비디오 엔진에 필수)")

    # Higgsfield 전용 엔진 (hailuo, wan 등)
    if video_engine in ("hailuo", "wan"):
        hf_key = os.getenv("HIGGSFIELD_API_KEY", "")
        hf_id = os.getenv("HIGGSFIELD_ACCOUNT_ID", "")
        if not hf_key or hf_key.startswith("YOUR"):
            errors.append(f"HIGGSFIELD_API_KEY ({video_engine} 비디오 엔진에 필수)")
        elif not hf_id or hf_id.startswith("YOUR"):
            errors.append("HIGGSFIELD_ACCOUNT_ID (Higgsfield 엔진에 필수)")

    if video_engine == "sora2":
        openai_check = api_key_override or os.getenv("OPENAI_API_KEY", "")
        if not openai_check or openai_check.startswith("sk-proj-YOUR"):
            errors.append("OPENAI_API_KEY (Sora 2 비디오 엔진에 필수)")

    return errors


@app.post("/api/generate")
async def generate_video_endpoint(req: GenerateRequest):
    topic = req.topic
    api_key_override = req.apiKey
    elevenlabs_key_override = req.elevenlabsKey
    video_engine = req.videoEngine
    image_engine = req.imageEngine
    llm_provider = req.llmProvider
    llm_key_override = req.llmKey
    output_path = req.outputPath
    language = req.language

    async def sse_generator():
        # 동시 요청 제한: 슬롯 부족 시 대기 안내
        acquired = False
        if _generate_semaphore.locked():
            yield {"data": "WARN|[대기열] 다른 비디오가 생성 중입니다. 순서를 기다리는 중...\n"}
        await _generate_semaphore.acquire()
        acquired = True
        try:
            # 사전 검증: 필수 API 키 확인
            missing = _validate_keys(api_key_override, elevenlabs_key_override, video_engine, image_engine, llm_provider, llm_key_override)
            if missing:
                yield {"data": "ERROR|[환경 설정 오류] 다음 API 키가 누락되었거나 유효하지 않습니다:\n"}
                for m in missing:
                    yield {"data": f"ERROR|  - {m}\n"}
                yield {"data": "ERROR|.env 파일을 확인하거나, 프론트엔드에서 API Key를 입력해주세요.\n"}
                return

            # 사전 검증: API 쿼터 체크 (경고만, 차단 안 함)
            el_key = elevenlabs_key_override or os.getenv("ELEVENLABS_API_KEY", "")
            quota_info = check_elevenlabs_quota(el_key)
            if quota_info:
                remaining = quota_info["remaining"]
                limit = quota_info["limit"]
                pct = (remaining / limit * 100) if limit > 0 else 0
                if remaining < 500:
                    yield {"data": f"WARN|[ElevenLabs 잔여 크레딧 부족] {remaining:,}/{limit:,}자 남음 ({pct:.0f}%). 생성이 중단될 수 있습니다.\n"}
                elif pct < 20:
                    yield {"data": f"WARN|[ElevenLabs 크레딧 경고] {remaining:,}/{limit:,}자 남음 ({pct:.0f}%).\n"}

            # Google 키 가용성 경고
            total_keys = count_google_keys()
            avail_keys = count_available_keys()
            if total_keys > 0 and avail_keys < total_keys:
                blocked_count = total_keys - avail_keys
                if avail_keys == 0:
                    yield {"data": f"WARN|[Google 키 경고] 모든 {total_keys}개 키가 429 차단됨. 쿼터 초과 가능성 높음.\n"}
                else:
                    yield {"data": f"WARN|[Google 키 상태] {avail_keys}/{total_keys}개 사용 가능 ({blocked_count}개 24시간 차단 중)\n"}

            provider_label = PROVIDER_LABELS.get(llm_provider, "ChatGPT")

            # 비디오 엔진 변수 초기화 (아래에서 키 선택·사전 검증에 사용)
            active_video_engine = video_engine

            # Google 키 로테이션 (비디오 엔진용 — 서비스별 차단 고려)
            video_svc = active_video_engine if active_video_engine in ("veo3",) else None
            google_key_for_video = get_google_key(llm_key_override, service=video_svc)

            # 비디오 엔진 사전 검증
            if active_video_engine != "none":
                engine_ok, engine_reason = check_engine_available(active_video_engine, google_key_for_video)
                if not engine_ok:
                    yield {"data": f"WARN|[비디오 엔진 경고] {active_video_engine}: {engine_reason}. 정지 이미지로 대체됩니다.\n"}
                    active_video_engine = "none"

            yield {"data": "PROG|10\n"}
            yield {"data": f"[기획 전문가] '{topic}' 쇼츠 기획 시작... ({provider_label} 엔진)\n"}

            # 단계 1: LLM 기획 (Gemini / ChatGPT / Claude 선택)
            # Gemini 프로바이더일 때 키 로테이션 적용
            llm_key_for_request = get_google_key(llm_key_override) if llm_provider == "gemini" else llm_key_override
            loop = asyncio.get_running_loop()
            cuts, topic_folder = await loop.run_in_executor(
                None,
                lambda: generate_cuts(
                    topic,
                    api_key_override=api_key_override,
                    lang=language,
                    llm_provider=llm_provider,
                    llm_key_override=llm_key_for_request,
                ),
            )

            yield {"data": "PROG|30\n"}
            yield {"data": f"[기획 완료] 총 {len(cuts)}컷 기획 완료!\n"}

            # 단계 2 & 3: 이미지와 TTS 병렬 처리 (Threading)
            image_label = "Imagen 4" if image_engine == "imagen" else "DALL-E"
            yield {"data": f"[생성 엔진] 아트 디렉터({image_label})와 성우(TTS) 동시 작업 중...\n"}

            visual_paths = [None] * len(cuts)
            audio_paths = [None] * len(cuts)
            word_timestamps_list = [None] * len(cuts)
            scripts = [cut["script"] for cut in cuts]

            # 이미지/TTS 동시성 제한 (API 레이트 리밋 방지)
            image_semaphore = threading.Semaphore(2)  # 이미지 최대 2개 동시

            # 이미지 엔진에 따라 생성 함수 선택
            gen_image_fn = generate_image_imagen if image_engine == "imagen" else generate_image_dalle

            def _get_image_key():
                """이미지 생성 시마다 다른 키 사용 (로테이션)"""
                if image_engine == "imagen":
                    return get_google_key(llm_key_override, service="imagen")
                return api_key_override

            def process_cut(i, cut):
                # 에러 수집 (SSE로 전달할 상세 정보)
                errors = []

                # 이미지 생성 (세마포어로 동시성 제한)
                img_path = None
                with image_semaphore:
                    try:
                        cut_image_key = _get_image_key()
                        img_path = gen_image_fn(cut["prompt"], i, topic_folder, cut_image_key)
                    except Exception as exc:
                        errors.append(f"이미지: {exc}")
                        print(f"[컷 {i+1} 이미지 생성 실패] {exc}")

                # 비디오 변환과 TTS를 threading으로 병렬 실행 (데드락 방지: 직접 스레드 사용)
                video_result = [None]  # mutable container for thread result
                tts_result = [None]

                def _run_video():
                    try:
                        cut_video_key = get_google_key(llm_key_override, service=active_video_engine)
                        video_result[0] = generate_video_from_image(
                            img_path, cut["prompt"], i, topic_folder, active_video_engine, cut_video_key
                        )
                    except Exception as exc:
                        errors.append(f"비디오: {exc}")
                        print(f"[컷 {i+1} 비디오 변환 실패] {exc}")

                def _run_tts():
                    try:
                        tts_result[0] = generate_tts(cut["script"], i, topic_folder, elevenlabs_key_override, language=language)
                    except Exception as exc:
                        errors.append(f"TTS: {exc}")
                        print(f"[컷 {i+1} TTS 생성 실패] {exc}")

                threads = []
                if img_path and active_video_engine != "none":
                    t = threading.Thread(target=_run_video, daemon=True)
                    t.start()
                    threads.append(t)
                t_tts = threading.Thread(target=_run_tts, daemon=True)
                t_tts.start()
                threads.append(t_tts)

                # 완료 대기 (비디오: 최대 5분, TTS: 최대 1분)
                for t in threads:
                    t.join(timeout=300)

                final_visual_path = video_result[0] if video_result[0] else img_path

                # Whisper 타임스탬프 (TTS 완료 후 순차)
                aud_path = tts_result[0]
                words = []
                if aud_path:
                    try:
                        words = generate_word_timestamps(aud_path, api_key_override, language=language)
                    except Exception as exc:
                        errors.append(f"타임스탬프: {exc}")
                        print(f"[컷 {i+1} 타임스탬프 추출 실패] {exc}")
                return i, final_visual_path, aud_path, words, errors

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

            yield {"data": "PROG|85\n"}
            yield {"data": "[렌더링 마스터] Remotion (React) 동적 화면 및 호르모지 스타일 자막 합성 렌더링 시작...\n"}

            # 단계 4: Remotion 비디오 렌더링
            video_path = await loop.run_in_executor(
                None,
                create_remotion_video,
                visual_paths,
                audio_paths,
                scripts,
                word_timestamps_list,
                topic_folder,
            )

            if not video_path:
                yield {"data": "ERROR|[Remotion 오류] 영상 렌더링에 실패했습니다. remotion 폴더에서 'npm install'이 완료되었는지 확인해주세요.\n"}
                return

            final_abs_path = os.path.abspath(video_path)
            if not os.path.exists(final_abs_path):
                yield {"data": f"ERROR|[파일 오류] 렌더링 성공 응답을 받았지만 파일이 없습니다: {final_abs_path}\n"}
                return

            yield {"data": "PROG|100\n"}

            # 사용자 지정 저장 경로가 있으면 복사 (경로 검증 포함)
            if output_path:
                abs_output = os.path.abspath(output_path)
                safe_base = os.path.abspath("assets")
                home_dir = os.path.expanduser("~")
                # 허용: assets/ 내부 또는 사용자 홈 디렉토리 하위
                if not (abs_output.startswith(safe_base + os.sep) or abs_output.startswith(home_dir + os.sep)):
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

            # Downloads 폴더로 자동 복사
            final_filename = os.path.basename(video_path)
            downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
            downloads_path = None
            if os.path.isdir(downloads_dir):
                try:
                    downloads_path = os.path.join(downloads_dir, final_filename)
                    await asyncio.to_thread(shutil.copy2, final_abs_path, downloads_path)
                except Exception as cp_err:
                    print(f"[Downloads 복사 실패] {cp_err}")
                    downloads_path = None

            # 프론트엔드 라우팅용 경로 (StaticFiles mount 기준)
            relative_video_path = f"/assets/{topic_folder}/video/{final_filename}"

            if downloads_path and os.path.exists(downloads_path):
                yield {"data": f"[완료] 최종 비디오 렌더링 대성공! 📂 Downloads 폴더에 저장됨: {final_filename}\n"}
            else:
                yield {"data": f"[완료] 최종 비디오 렌더링 대성공! 경로: {relative_video_path}\n"}
            yield {"data": f"DONE|{relative_video_path}\n"}

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
                yield {"data": f"ERROR|[시스템 오류] {err_str}\n"}
        finally:
            if acquired:
                _generate_semaphore.release()

    return EventSourceResponse(sse_generator())


@app.on_event("shutdown")
async def _shutdown():
    _cut_executor.shutdown(wait=False)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
