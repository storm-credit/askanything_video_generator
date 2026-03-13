import os
import time
from openai import OpenAI


MAX_RETRIES = 2
RETRY_DELAY = 3


def generate_word_timestamps(audio_path, api_key=None):
    """
    주어진 오디오 파일에서 Whisper API를 이용해 단어 단위 타임스탬프를 추출합니다.
    타임아웃/네트워크 오류 시 최대 2회 재시도.
    """
    final_api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not final_api_key:
        raise EnvironmentError("OpenAI API 키가 제공되지 않았습니다.")

    client = OpenAI(api_key=final_api_key)

    if not audio_path:
        print(f"[Whisper 오류] 오디오 경로가 비어 있습니다.")
        return []
    try:
        file_stat = os.stat(audio_path)
        if file_stat.st_size == 0:
            print(f"[Whisper 오류] 오디오 파일이 비어 있습니다: {audio_path}")
            return []
    except FileNotFoundError:
        print(f"[Whisper 오류] 오디오 파일이 없습니다: {audio_path}")
        return []

    for attempt in range(MAX_RETRIES):
        try:
            label = f"(시도 {attempt+1}/{MAX_RETRIES})" if attempt > 0 else ""
            print(f"-> [동적 자막] Whisper API 타임스탬프 추출 중... ({os.path.basename(audio_path)}) {label}")

            with open(audio_path, "rb") as audio_file:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="verbose_json",
                    timestamp_granularities=["word"]
                )

            if hasattr(transcript, "words") and transcript.words:
                return [{"word": w["word"], "start": w["start"], "end": w["end"]} for w in transcript.words]
            elif isinstance(transcript, dict) and "words" in transcript:
                return transcript["words"]
            else:
                try:
                    data = transcript.model_dump()
                    return data.get("words", [])
                except Exception:
                    return []

        except Exception as e:
            print(f"[Whisper 오류] {e} ({attempt+1}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY)
                continue
            return []

    return []
