import os
from openai import OpenAI

def generate_word_timestamps(audio_path, api_key=None):
    """
    주어진 오디오 파일에서 Whisper API를 이용해 단어 단위 타임스탬프를 추출합니다.
    """
    final_api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not final_api_key:
        raise EnvironmentError("OpenAI API 키가 제공되지 않았습니다.")
        
    client = OpenAI(api_key=final_api_key)
    
    if not os.path.exists(audio_path):
        return []
        
    try:
        print(f"-> [동적 자막] Whisper API 타임스탬프 추출 중... ({os.path.basename(audio_path)})")
        with open(audio_path, "rb") as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["word"]
            )
            
        # 단어 리스트 반환 (예: [{"word": "블랙홀", "start": 0.0, "end": 0.5}, ...])
        if hasattr(transcript, "words") and transcript.words:
            return [{"word": w["word"], "start": w["start"], "end": w["end"]} for w in transcript.words]
        elif isinstance(transcript, dict) and "words" in transcript:
            return transcript["words"]
        else:
            # Pydantic v2 호환성을 위해 dict 변환 시도
            try:
                data = transcript.model_dump()
                return data.get("words", [])
            except:
                return []
    except Exception as e:
        print(f"[Whisper 오류] {e}")
        return []
