import os
import sys
import io
import asyncio
from fastapi import FastAPI
from sse_starlette.sse import EventSourceResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
load_dotenv(override=True)

from modules.gpt.cutter import generate_cuts
from modules.image.dalle import generate_image
from modules.video.kling import generate_video_from_image
from modules.tts.elevenlabs import generate_tts
from modules.transcription.whisper import generate_word_timestamps
from modules.video.remotion import create_remotion_video

app = FastAPI()

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
    topic: str
    apiKey: str | None = None


@app.post("/api/generate")
async def generate_video_endpoint(req: GenerateRequest):
    topic = req.topic
    api_key_override = req.apiKey

    async def sse_generator():
        try:
            yield {"data": "PROG|10\n"}
            yield {"data": f"[기획 전문가] '{topic}' 쇼츠 기획 시작...\n"}

            # 단계 1: GPT 기획
            loop = asyncio.get_event_loop()
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
                img_path = generate_image(cut["prompt"], i, topic_folder, api_key_override)
                kling_path = None
                if img_path:
                    # DALL-E 이미지 -> Kling 시네마틱 비디오 클라우드 렌더링
                    kling_path = generate_video_from_image(img_path, cut["prompt"], i, topic_folder)

                # Kling 변환 실패 시 기존 이미지로 폴백
                final_visual_path = kling_path if kling_path else img_path

                aud_path = generate_tts(cut["script"], i, topic_folder)
                words = generate_word_timestamps(aud_path, api_key_override) if aud_path else []
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
                yield {"data": f"  -> 컷 {i+1} 시각 소스(Kling/DALL-E) 및 음성 생성 완료\n"}

            if any(p is None for p in visual_paths) or any(p is None for p in audio_paths):
                yield {"data": "ERROR|[소스 생성 오류] 일부 컷의 이미지/오디오 생성이 실패했습니다. API 키 및 네트워크 상태를 확인해주세요.\n"}
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
            yield {"data": f"ERROR|[시스템 오류] {str(e)}\n"}

    return EventSourceResponse(sse_generator())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
