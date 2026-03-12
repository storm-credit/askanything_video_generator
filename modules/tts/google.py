from gtts import gTTS
import os

def generate_tts(text, index, topic_folder):
    # 예: assets/벌은_잠을_잘까/audio
    output_dir = os.path.join("assets", topic_folder, "audio")
    os.makedirs(output_dir, exist_ok=True)

    filename = os.path.join(output_dir, f"cut_{index:02}.mp3")

    try:
        if not text.strip():
            raise ValueError(f"[TTS 오류] 빈 텍스트로 TTS 생성 불가 (index={index})")

        tts = gTTS(text=text, lang="ko")
        tts.save(filename)

        if not os.path.exists(filename):
            raise FileNotFoundError(f"[TTS 오류] 파일 저장 실패: {filename}")

        return filename

    except Exception as e:
        print(f"[TTS 오류] cut_{index:02}: {e}")
        return None  # 예외 발생 시 fallback 처리 가능
