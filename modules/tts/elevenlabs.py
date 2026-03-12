import os
import requests

def generate_tts(text: str, index: int, topic_folder: str, api_key_override: str = None) -> str:
    """
    ElevenLabs API를 사용하여 매우 사실적인 다큐멘터리/쇼츠용 음성(.mp3)을 생성합니다.
    (OpenAI TTS 'onyx' 스타일을 대체)
    """
    api_key = api_key_override or os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        print("[ElevenLabs 오류] API Key가 제공되지 않았습니다.")
        return None

    # 가장 다큐멘터리/내레이션에 적합한 Voice ID (예: 'Brian' 또는 'Drew' 같은 깊고 중후한 남성 목소리)
    # 여기서는 ElevenLabs에서 기본 제공하는 대중적인 내레이션 목소리 ID 중 하나를 사용합니다. 
    # 'pNInz6obpgDQGcFmaJcg' = Adam (중후하고 신뢰감 있는 목소리)
    # 'cjVigY5qzO86Huf0OWal' = Eric (다큐멘터리 톤)
    VOICE_ID = "cjVigY5qzO86Huf0OWal" # Eric
    URL = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key
    }

    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True
        }
    }

    output_dir = os.path.join("assets", topic_folder, "audio")
    os.makedirs(output_dir, exist_ok=True)
    audio_path = os.path.join(output_dir, f"cut_{index}.mp3")

    print(f"-> [초호화 성우 엔진 (ElevenLabs)] 컷 {index+1} 내레이션 렌더링 중...")
    try:
        response = requests.post(URL, json=data, headers=headers, timeout=30)
        
        if response.status_code == 200:
            with open(audio_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
            print(f"OK [초호화 성우 엔진 (ElevenLabs)] 컷 {index+1} 음성 생성 완료!")
            return audio_path
        else:
            print(f"[ElevenLabs 오류] 요청 실패 ({response.status_code}): {response.text}")
            return None
    except Exception as e:
        print(f"[ElevenLabs 통신 오류] {e}")
        return None
