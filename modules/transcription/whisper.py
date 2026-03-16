import os
import time
import random
from openai import OpenAI


MAX_RETRIES = 2


def generate_word_timestamps(audio_path: str, api_key: str | None = None, language: str = "ko") -> list[dict]:
    """
    주어진 오디오 파일에서 Whisper API를 이용해 단어 단위 타임스탬프를 추출합니다.
    타임아웃/네트워크 오류 시 최대 2회 재시도.
    """
    final_api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not final_api_key:
        raise EnvironmentError("OpenAI API 키가 제공되지 않았습니다.")

    client = OpenAI(api_key=final_api_key)

    if not audio_path:
        print("[Whisper 오류] 오디오 경로가 비어 있습니다.")
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
                    language=language,
                    response_format="verbose_json",
                    timestamp_granularities=["word"]
                )

            # OpenAI SDK v1.x: TranscriptionWord는 Pydantic 모델 (속성/딕셔너리 접근 모두 가능)
            raw_words = None
            if hasattr(transcript, "words") and transcript.words:
                raw_words = transcript.words
            elif isinstance(transcript, dict) and "words" in transcript:
                raw_words = transcript["words"]
            else:
                try:
                    data = transcript.model_dump()
                    raw_words = data.get("words", [])
                except Exception as dump_err:
                    print(f"[Whisper 경고] model_dump() 실패: {dump_err}")

            words = []
            if not raw_words:
                print(f"[Whisper 경고] API 응답에 word timestamp가 없습니다 ({os.path.basename(audio_path)}). 응답 타입: {type(transcript).__name__}")
            else:
                for w in raw_words:
                    try:
                        if isinstance(w, dict):
                            words.append({"word": str(w["word"]), "start": float(w["start"]), "end": float(w["end"])})
                        else:
                            words.append({"word": str(w.word), "start": float(w.start), "end": float(w.end)})
                    except Exception as parse_err:
                        print(f"[Whisper 경고] 단어 파싱 실패 (건너뜀): {parse_err} | 원본: {w}")
                        continue

            if words:
                print(f"OK [동적 자막] {len(words)}개 단어 타임스탬프 추출 완료 ({os.path.basename(audio_path)})")
            else:
                print(f"[Whisper 경고] 단어 타임스탬프가 비어 있습니다 ({os.path.basename(audio_path)})")
            return words

        except Exception as e:
            print(f"[Whisper 오류] {e} ({attempt+1}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES - 1:
                time.sleep(min(2 ** (attempt + 1), 8) + random.uniform(0, 1))
                continue
            return []
