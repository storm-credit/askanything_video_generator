import os
import sys
import io
import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
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
    apiKey: str = None


@app.get("/api/preflight")
def preflight_check():
    """현재 실행 환경에서 자주 막히는 포인트를 빠르게 진단합니다."""
    checks = {
        "openai_key": bool(os.getenv("OPENAI_API_KEY")),
        "elevenlabs_key": bool(os.getenv("ELEVENLABS_API_KEY")),
        "tavily_key": bool(os.getenv("TAVILY_API_KEY")),
        "remotion_package_json": os.path.exists(os.path.join("remotion", "package.json")),
        "remotion_node_modules": os.path.exists(os.path.join("remotion", "node_modules")),
    }
    checks["ready"] = all([
        checks["openai_key"],
        checks["remotion_package_json"],
        checks["remotion_node_modules"],
    ])
    return JSONResponse(content=checks)

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
            yield {"data": f"[생성 엔진] 아트 디렉터(DALL-E)와 성우(TTS) 동시 작업 중...\n"}
            
            visual_paths = [None] * len(cuts)
            audio_paths = [None] * len(cuts)
            word_timestamps_list = [None] * len(cuts)
            scripts = [cut["script"] for cut in cuts]
            
            # 병렬 처리를 위한 작업 정의
            def process_cut(i, cut):
                img_path = generate_image(cut["prompt"], i, topic_folder, api_key_override)
                kling_path = None
                if img_path:
                    # DALL-E 이미지 -> Kling 시네마틱 비디오 클라우드 렌더링
                    kling_path = generate_video_from_image(img_path, cut["prompt"], i, topic_folder)
                
                # Kling 변환 실패 시 기존 이미지로 폴백
                final_visual_path = kling_path if kling_path else img_path
                
                aud_path = generate_tts(cut["script"], i, topic_folder, api_key_override)
                words = generate_word_timestamps(aud_path, api_key_override) if aud_path else []
                return i, final_visual_path, aud_path, words

            # 비동기 Non-blocking 이벤트 루프 실행 (SSE flush 보장)
            tasks = [loop.run_in_executor(None, process_cut, i, cut) for i, cut in enumerate(cuts)]
            completed_count = 0
            
            import asyncio
            for future in asyncio.as_completed(tasks):
                i, final_visual_path, aud_path, words = await future
                visual_paths[i] = final_visual_path
                audio_paths[i] = aud_path
                word_timestamps_list[i] = words
                
                completed_count += 1
                prog = 30 + int(50 * (completed_count / len(cuts)))
                yield {"data": f"PROG|{prog}\n"}
                yield {"data": f"  -> 컷 {i+1} 시각 소스(Kling/DALL-E) 및 음성 생성 완료\n"}

            yield {"data": "PROG|85\n"}
            yield {"data": "[렌더링 마스터] Remotion (React) 동적 화면 및 호르모지 스타일 자막 합성 렌더링 시작...\n"}
            
            # 단계 4: Remotion 비디오 렌더링
            video_path = await loop.run_in_executor(
                None, 
                create_remotion_video, 
                visual_paths, audio_paths, scripts, word_timestamps_list, topic_folder
            )
            
            if not video_path:
                yield {"data": "ERROR|[Remotion 오류] 영상 렌더링에 실패했습니다. remotion 폴더에서 'npm install'이 완료되었는지 확인해주세요.\n"}
                return
                
            yield {"data": "PROG|100\n"}
            
            # 절대 경로를 프론트엔드 라우팅용 상대 경로로 변환 (Windows 역슬래시 방어)
            final_filename = os.path.basename(video_path)
            relative_video_path = f"assets/{topic_folder}/video/{final_filename}"
            
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
