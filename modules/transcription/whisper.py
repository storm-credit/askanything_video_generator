import os
import re
import time
import random
from openai import OpenAI


MAX_RETRIES = 2


def align_words_with_script(whisper_words: list[dict], script: str) -> list[dict]:
    """Whisper 타임스탬프에 원본 스크립트 텍스트를 매핑.

    Whisper가 외래어를 잘못 인식할 수 있으므로 (오무아무아→웅하마),
    타임스탬프(시간)는 Whisper 것을 쓰고 단어 텍스트는 원본 스크립트를 사용.
    """
    if not whisper_words or not script:
        return whisper_words

    # 원본 스크립트를 단어로 분리
    script_words = script.split()
    if not script_words:
        return whisper_words

    # 단어 수가 비슷하면 1:1 매핑
    if abs(len(script_words) - len(whisper_words)) <= 2:
        aligned = []
        for i, w in enumerate(whisper_words):
            word_text = script_words[i] if i < len(script_words) else w["word"]
            aligned.append({"word": word_text, "start": w["start"], "end": w["end"]})
        return aligned

    # 단어 수 차이가 크면 Whisper 원본 유지 (안전)
    return whisper_words


def generate_word_timestamps(audio_path: str, api_key: str | None = None, language: str = "ko") -> list[dict]:
    """
    주어진 오디오 파일에서 Whisper API를 이용해 단어 단위 타임스탬프를 추출합니다.
    타임아웃/네트워크 오류 시 최대 2회 재시도.
    """
    final_api_key = api_key or os.getenv("OPENAI_API_KEY")
    if not final_api_key:
        raise EnvironmentError("OpenAI API 키가 제공되지 않았습니다.")

    client = OpenAI(api_key=final_api_key, timeout=120)

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

            raw_words = getattr(transcript, "words", None) or []

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
