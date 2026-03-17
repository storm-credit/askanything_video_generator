import os
import sys
from dotenv import load_dotenv

import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

load_dotenv(override=True)

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from modules.gpt.cutter import generate_cuts
from modules.image.dalle import generate_image
from modules.video.kling import generate_video_from_image
from modules.tts.elevenlabs import generate_tts
from modules.transcription.whisper import generate_word_timestamps
from modules.video.remotion import create_remotion_video

def run_test():
    topic = "무지개는 왜 생길까? 간단 테스트"
    print(f"-> 테스트 주제: {topic}")
    
    try:
        # GPT 컷 분할
        print("\n[1단계] GPT 컷 생성 중...")
        cuts, topic_folder, _title, _tags, _seo = generate_cuts(topic)
        print(f"OK 생성된 컷 수: {len(cuts)}")
        
        # 제한 해제: 전체 컷을 테스트합니다.
        # cuts = cuts[:2]
        
        visual_paths = []
        audio_paths = []
        scripts = []
        word_timestamps_list = []
        
        for i, cut in enumerate(cuts):
            print(f"\n-> 컷 {i+1} 처리 중...")
            
            # 1. 이미지 생성 (DALL-E)
            print("  - 이미지 생성 중...")
            image_path = generate_image(cut["prompt"], i, topic_folder)
            
            # 2. 비디오 변환 (Kling)
            print("  - Kling 비디오 생성 중...")
            kling_path = None
            if image_path:
                kling_path = generate_video_from_image(image_path, cut["prompt"], i, topic_folder)
            final_visual_path = kling_path if kling_path else image_path
            visual_paths.append(final_visual_path)
            
            # 3. 오디오 생성 (ElevenLabs)
            print("  - TTS 오디오 생성 중...")
            script_text = cut["script"]
            audio_path = generate_tts(script_text, i, topic_folder)
            audio_paths.append(audio_path)
            scripts.append(script_text)
            
            # 4. Whisper 타임스탬프 추출
            print("  - 단어 타임스탬프 추출 중...")
            words = generate_word_timestamps(audio_path) if audio_path else []
            word_timestamps_list.append(words)
            
            print(f"OK 컷 {i+1} 처리 완료")
            
        # 5. 비디오 렌더링 (Remotion)
        print("\n[최종 단계] Remotion 비디오 렌더링 중...")
        video_path = create_remotion_video(visual_paths, audio_paths, scripts, word_timestamps_list, topic_folder, title=_title)
        
        if video_path:
            print(f"SUCCESS 성공! 비디오 생성 완료: {video_path}")
        else:
            print("ERROR 렌더링 실패.")
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"ERROR 오류 발생: {e}")

if __name__ == "__main__":
    run_test()
