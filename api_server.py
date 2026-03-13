import os
import sys
import io
import asyncio
from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
load_dotenv(override=True)

from modules.gpt.cutter import generate_cuts
from modules.image.dalle import generate_image
from modules.video.engines import generate_video_from_image, get_available_engines
from modules.tts.elevenlabs import generate_tts
from modules.transcription.whisper import generate_word_timestamps
from modules.video.remotion import create_remotion_video

app = FastAPI()


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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=500)
    apiKey: str | None = None
    elevenlabsKey: str | None = None
    videoEngine: str = "kling"

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


@app.get("/api/engines")
async def list_engines():
    return get_available_engines()


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
    hf_key = os.getenv("HIGGSFIELD_API_KEY", "")
    hf_id = os.getenv("HIGGSFIELD_ACCOUNT_ID", "")
    kling_ak = os.getenv("KLING_ACCESS_KEY", "")
    kling_sk = os.getenv("KLING_SECRET_KEY", "")

    keys = {
        "openai": _is_set(openai_key, ["sk-proj-YOUR"]),
        "elevenlabs": _is_set(elevenlabs_key, ["YOUR_ELEVENLABS_API_KEY_HERE"]),
        "higgsfield_key": _is_set(hf_key, ["YOUR"]),
        "higgsfield_account": _is_set(hf_id, ["YOUR"]),
        "kling_access": _is_set(kling_ak, ["YOUR"]),
        "kling_secret": _is_set(kling_sk, ["YOUR"]),
    }

    missing = [k for k, v in keys.items() if not v]
    return {
        "status": "ok" if not missing else "missing_keys",
        "keys": keys,
        "missing": missing,
    }


def _validate_keys(api_key_override: str | None, elevenlabs_key_override: str | None, video_engine: str) -> list[str]:
    """파이프라인 시작 전 필수 키 검증. 누락된 키 이름 목록을 반환."""
    errors = []
    openai_key = api_key_override or os.getenv("OPENAI_API_KEY", "")
    if not openai_key or openai_key.startswith("sk-proj-YOUR"):
        errors.append("OPENAI_API_KEY (GPT 기획 + DALL-E 이미지 생성에 필수)")

    elevenlabs_key = elevenlabs_key_override or os.getenv("ELEVENLABS_API_KEY", "")
    if not elevenlabs_key or elevenlabs_key == "YOUR_ELEVENLABS_API_KEY_HERE":
        errors.append("ELEVENLABS_API_KEY (TTS 음성 생성에 필수)")

    if video_engine in ("kling", "veo3", "hailuo", "wan"):
        hf_key = os.getenv("HIGGSFIELD_API_KEY", "")
        hf_id = os.getenv("HIGGSFIELD_ACCOUNT_ID", "")
        if not hf_key or hf_key.startswith("YOUR"):
            if video_engine == "kling":
                kling_ak = os.getenv("KLING_ACCESS_KEY", "")
                if not kling_ak or kling_ak.startswith("YOUR"):
                    errors.append(f"HIGGSFIELD_API_KEY 또는 KLING_ACCESS_KEY ({video_engine} 비디오 엔진에 필수)")
            else:
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

    async def sse_generator():
        try:
            # 사전 검증: 필수 API 키 확인
            missing = _validate_keys(api_key_override, elevenlabs_key_override, video_engine)
            if missing:
                yield {"data": "ERROR|[환경 설정 오류] 다음 API 키가 누락되었거나 유효하지 않습니다:\n"}
                for m in missing:
                    yield {"data": f"ERROR|  - {m}\n"}
                yield {"data": "ERROR|.env 파일을 확인하거나, 프론트엔드에서 API Key를 입력해주세요.\n"}
                return

            yield {"data": "PROG|10\n"}
            yield {"data": f"[기획 전문가] '{topic}' 쇼츠 기획 시작...\n"}

            # 단계 1: GPT 기획
            loop = asyncio.get_running_loop()
            cuts, topic_folder = await loop.run_in_executor(None, generate_cuts, topic, api_key_override)

            yield {"data": "PROG|30\n"}
            yield {"data": f"[기획 완료] 총 {len(cuts)}컷 기획 완료!\n"}

            # 단계 2 & 3: DALL-E와 TTS 병렬 처리 (Threading)
            yield {"data": "[생성 엔진] 아트 디렉터(DALL-E)와 성우(TTS) 동시 작업 중...\n"}

            visual_paths = [None] * len(cuts)
            audio_paths = [None] * len(cuts)
            word_timestamps_list = [None] * len(cuts)
            scripts = [cut["script"] for cut in cuts]

            def process_cut(i, cut):
                try:
                    img_path = generate_image(cut["prompt"], i, topic_folder, api_key_override)
                except Exception as exc:
                    print(f"[컷 {i+1} 이미지 생성 실패] {exc}")
                    img_path = None

                video_path = None
                if img_path and video_engine != "none":
                    try:
                        video_path = generate_video_from_image(img_path, cut["prompt"], i, topic_folder, engine=video_engine)
                    except Exception as exc:
                        print(f"[컷 {i+1} 비디오 변환 실패] {exc}")

                # 비디오 변환 실패 시 기존 이미지로 폴백
                final_visual_path = video_path if video_path else img_path

                try:
                    aud_path = generate_tts(cut["script"], i, topic_folder, elevenlabs_key_override)
                except Exception as exc:
                    print(f"[컷 {i+1} TTS 생성 실패] {exc}")
                    aud_path = None

                words = []
                if aud_path:
                    try:
                        words = generate_word_timestamps(aud_path, api_key_override)
                    except Exception as exc:
                        print(f"[컷 {i+1} 타임스탬프 추출 실패] {exc}")
                return i, final_visual_path, aud_path, words

            tasks = [loop.run_in_executor(None, process_cut, i, cut) for i, cut in enumerate(cuts)]
            completed_count = 0

            for future in asyncio.as_completed(tasks):
                i, final_visual_path, aud_path, words = await future
                visual_paths[i] = final_visual_path
                audio_paths[i] = aud_path
                word_timestamps_list[i] = words

                completed_count += 1
                prog = 30 + int(50 * (completed_count / len(cuts)))
                yield {"data": f"PROG|{prog}\n"}
                engine_label = video_engine if video_engine != "none" else "이미지"
                yield {"data": f"  -> 컷 {i+1} 시각 소스({engine_label}/DALL-E) 및 음성 생성 완료\n"}

            failed_visual = [i+1 for i, p in enumerate(visual_paths) if p is None]
            failed_audio = [i+1 for i, p in enumerate(audio_paths) if p is None]
            if failed_visual or failed_audio:
                details = []
                if failed_visual:
                    details.append(f"이미지 실패: 컷 {failed_visual}")
                if failed_audio:
                    details.append(f"오디오 실패: 컷 {failed_audio}")
                yield {"data": f"ERROR|[소스 생성 오류] {', '.join(details)}. API 키 및 네트워크 상태를 확인해주세요.\n"}
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

            # 프론트엔드 라우팅용 경로 (StaticFiles mount 기준)
            final_filename = os.path.basename(video_path)
            relative_video_path = f"/assets/{topic_folder}/video/{final_filename}"

            yield {"data": f"[완료] 최종 비디오 렌더링 대성공! 경로: {relative_video_path}\n"}
            yield {"data": f"DONE|{relative_video_path}\n"}

        except Exception as e:
            import traceback

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

    return EventSourceResponse(sse_generator())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
