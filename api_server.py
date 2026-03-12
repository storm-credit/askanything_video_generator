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

# 모듈 임포트
from modules.gpt.cutter import generate_cuts
from modules.image.dalle import generate_image
from modules.tts.google import generate_tts
from modules.video.ffmpeg import create_video

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
            
            image_paths = [None] * len(cuts)
            audio_paths = [None] * len(cuts)
            scripts = [cut["script"] for cut in cuts]
            
            # 병렬 처리를 위한 작업 정의
            def process_cut(i, cut):
                img_path = generate_image(cut["prompt"], i, topic_folder, api_key_override)
                aud_path = generate_tts(cut["script"], i, topic_folder, api_key_override)
                return i, img_path, aud_path

            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(process_cut, i, cut) for i, cut in enumerate(cuts)]
                for future in futures:
                    i, img_path, aud_path = future.result()
                    image_paths[i] = img_path
                    audio_paths[i] = aud_path
                    
                    # 진행률: 30% ~ 80% 사이를 분배
                    prog = 30 + int(50 * (len([p for p in image_paths if p is not None]) / len(cuts)))
                    yield {"data": f"PROG|{prog}\n"}
                    yield {"data": f"  -> 컷 {i+1} 이미지 및 음성 생성 완료\n"}

            yield {"data": "PROG|85\n"}
            yield {"data": "[렌더링 마스터] FFmpeg 동적 화면(Zoom) 및 자막 렌더링 시작...\n"}
            
            # 단계 4: FFmpeg 병합
            video_path = await loop.run_in_executor(
                None, 
                create_video, 
                image_paths, audio_paths, scripts, topic_folder
            )
            
            yield {"data": "PROG|100\n"}
            yield {"data": f"[완료] 최종 비디오 렌더링 대성공! 경로: {video_path}\n"}
            yield {"data": f"DONE|{video_path}\n"}
            
        except Exception as e:
            import traceback
            traceback.print_exc()
            yield {"data": f"ERROR|[시스템 오류] {str(e)}\n"}

    return EventSourceResponse(sse_generator())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=True)
