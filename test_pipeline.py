import os
import sys
from dotenv import load_dotenv

import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv(override=True)

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from modules.gpt.cutter import generate_cuts
from modules.image.dalle import generate_image
from modules.tts.google import generate_tts
from modules.video.ffmpeg import create_video

def run_test():
    topic = "무지개는 왜 생길까? 간단 테스트"
    print(f"-> 테스트 주제: {topic}")
    
    try:
        # GPT 컷 분할
        print("\n[1단계] GPT 컷 생성 중...")
        cuts, topic_folder = generate_cuts(topic)
        print(f"OK 생성된 컷 수: {len(cuts)}")
        
        # 컷 수를 최대 2컷으로 제한 (초고속 테스트용)
        cuts = cuts[:2]
        
        image_paths = []
        audio_paths = []
        scripts = []
        
        for i, cut in enumerate(cuts):
            print(f"\n-> 컷 {i+1} 처리 중...")
            
            # 이미지 생성
            print("  - 이미지 생성 중...")
            image_path = generate_image(cut["prompt"], i, topic_folder)
            image_paths.append(image_path)
            
            # 스크립트 및 TTS 생성
            print("  - TTS 오디오 생성 중...")
            script_text = cut["script"]
            audio_path = generate_tts(script_text, i, topic_folder)
            audio_paths.append(audio_path)
            scripts.append(script_text)
            
            print(f"OK 컷 {i+1} 처리 완료")
            
        # 비디오 병합
        print("\n[최종 단계] 비디오 생성 중...")
        video_path = create_video(image_paths, audio_paths, scripts, topic_folder)
        print(f"SUCCESS 성공! 비디오 생성 완료: {video_path}")
        
    except Exception as e:
        print(f"ERROR 오류 발생: {e}")

if __name__ == "__main__":
    run_test()
