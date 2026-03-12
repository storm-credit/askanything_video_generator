import os
from openai import OpenAI

# 하위 호환성을 위해 이름 유지 (실제로는 OpenAI 기반 동작)
def generate_tts(text, index, topic_folder):
    # 예: assets/주제/audio
    output_dir = os.path.join("assets", topic_folder, "audio")
    os.makedirs(output_dir, exist_ok=True)

    filename = os.path.join(output_dir, f"cut_{index:02}.mp3")

    try:
        if not text.strip():
            raise ValueError(f"[TTS 오류] 빈 텍스트로 TTS 생성 불가 (index={index})")

        print(f"-> [오디오 디렉터] 컷 {index+1} 내레이션 렌더링 중 (다큐멘터리 성우 톤)...")
        
        # 클라이언트 초기화
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError("환경변수 OPENAI_API_KEY가 설정되어 있지 않습니다.")
        client = OpenAI(api_key=api_key)

        # 내셔널 지오그래픽 감성: 'onyx' (중저음, 신뢰감 있고 웅장한 목소리)
        response = client.audio.speech.create(
            model="tts-1",
            voice="onyx",
            input=text
        )
        
        response.stream_to_file(filename)

        if not os.path.exists(filename):
            raise FileNotFoundError(f"[TTS 오류] 파일 저장 실패: {filename}")

        return filename

    except Exception as e:
        print(f"[TTS 오류] cut_{index:02}: {e}")
        return None
