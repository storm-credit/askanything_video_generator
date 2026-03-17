import os
import time
import random
from openai import OpenAI


MAX_RETRIES = 2

# 타임스탬프 정규화 상수 (Eye-tracking 자막 인지 연구, Dec 2024 기반)
_MIN_WORD_DURATION = 0.20   # 최소 단어 표시 시간 (200ms)
_MAX_WORD_DURATION = 0.80   # 최대 단어 표시 시간 (800ms)
_PRE_DISPLAY_OFFSET = 0.05  # 음성보다 50ms 먼저 표시 (가독성 향상)


def _normalize_timestamps(words: list[dict]) -> list[dict]:
    """Whisper 타임스탬프를 정규화합니다.
    - 최소/최대 표시 시간 보장
    - 50ms 선행 오프셋 (자막이 음성보다 약간 먼저 표시)
    - 겹침 방지
    """
    if not words:
        return words

    # 마지막 단어의 원래 end를 상한으로 사용 (오디오 길이 초과 방지)
    original_last_end = words[-1]["end"]

    normalized = []
    for i, w in enumerate(words):
        start = max(0, w["start"] - _PRE_DISPLAY_OFFSET)
        end = w["end"]
        duration = end - start

        # 최소 표시 시간 보장
        if duration < _MIN_WORD_DURATION:
            end = start + _MIN_WORD_DURATION

        # 최대 표시 시간 제한
        if end - start > _MAX_WORD_DURATION:
            end = start + _MAX_WORD_DURATION

        # 이전 단어와 겹침 방지
        if normalized and start < normalized[-1]["end"]:
            start = normalized[-1]["end"]
            if end <= start:
                end = start + _MIN_WORD_DURATION

        # 마지막 단어는 원래 오디오 끝을 초과하지 않도록 클램핑
        if i == len(words) - 1 and end > original_last_end + _MIN_WORD_DURATION:
            end = max(start + _MIN_WORD_DURATION, original_last_end)

        normalized.append({"word": w["word"], "start": round(start, 3), "end": round(end, 3)})

    return normalized


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

            # 타임스탬프 정규화 (Eye-tracking 연구 기반: 최소 200ms + 50ms 선행 오프셋)
            if words:
                words = _normalize_timestamps(words)
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
