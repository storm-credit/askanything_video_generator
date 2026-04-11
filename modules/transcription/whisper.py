import os
import re
import time
import random
from openai import OpenAI


MAX_RETRIES = 2


def _normalize_word(word: str) -> str:
    """구두점·특수문자 제거, 소문자 변환 (언어 무관)."""
    return re.sub(r'[^\w\uAC00-\uD7A3\u4E00-\u9FFF\u30A0-\u30FF\u00C0-\u024F]', '', word).lower()


def _lcs_anchors(src: list[str], tgt: list[str]) -> list[tuple[int, int]]:
    """LCS로 (src_idx, tgt_idx) 공통 앵커 추출.

    정규화된 단어 기준으로 매칭 — 구두점/대소문자 차이 무시.
    O(m×n) DP. 단어 수가 많으면 슬라이딩 윈도우로 제한.
    """
    m, n = len(src), len(tgt)
    # 너무 긴 경우 윈도우 슬라이딩으로 근사 (성능 보호)
    if m * n > 4000:
        return _lcs_anchors_windowed(src, tgt, window=30)

    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if src[i - 1] == tgt[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])

    anchors: list[tuple[int, int]] = []
    i, j = m, n
    while i > 0 and j > 0:
        if src[i - 1] == tgt[j - 1]:
            anchors.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif dp[i - 1][j] > dp[i][j - 1]:
            i -= 1
        else:
            j -= 1
    return list(reversed(anchors))


def _lcs_anchors_windowed(src: list[str], tgt: list[str], window: int = 30) -> list[tuple[int, int]]:
    """긴 시퀀스용 — 슬라이딩 윈도우 내에서만 LCS 탐색."""
    anchors: list[tuple[int, int]] = []
    j_start = 0
    for i, sw in enumerate(src):
        j_end = min(j_start + window, len(tgt))
        for j in range(j_start, j_end):
            if tgt[j] == sw:
                anchors.append((i, j))
                j_start = j + 1
                break
    return anchors


def _interpolate_segment(
    words: list[str],
    t_start: float,
    t_end: float,
) -> list[dict]:
    """구간 내 단어들에 글자 수 비례로 타임스탬프 배분."""
    if not words:
        return []
    char_counts = [max(len(w), 1) for w in words]
    total_chars = sum(char_counts)
    duration = max(t_end - t_start, 0.08 * len(words))
    t = t_start
    result = []
    for w, chars in zip(words, char_counts):
        dur = duration * chars / total_chars
        result.append({"word": w, "start": round(t, 3), "end": round(t + dur, 3)})
        t += dur
    return result


def align_words_with_script(whisper_words: list[dict], script: str, lang: str = "ko") -> list[dict]:
    """Whisper 타임스탬프 + 원본 스크립트 텍스트를 LCS 기반으로 정렬.

    전략:
      1. 단어 수 차이 ≤ 2: 기존 1:1 매핑 (빠름, 정확)
      2. 차이 > 2: LCS 앵커 매칭 + 앵커 사이 글자 수 비례 보간
         → 모든 자막이 원본 스크립트 텍스트로 표시됨 (오인식 완전 방지)

    언어별 오류 특성:
      KO ★★★: 복합어 분리, 외래어 오인식 (오무아무아→웅하마)
      ES ★★☆: 장단어 분리 차이 (desaparecieron → 3단어)
      EN ★☆☆: 대체로 정확, 고유명사 일부
    """
    if not whisper_words or not script:
        return whisper_words

    script_words = script.split()
    if not script_words:
        return whisper_words

    # ── Case 1: 단어 수 정확히 같거나 1개 차이 → 단순 1:1 교체 ──────────
    # 차이 2 이상은 LCS 정렬로 (잘못된 타임스탬프 보간 방지)
    if abs(len(script_words) - len(whisper_words)) <= 1:
        aligned = []
        # Whisper > Script: script 단어 수만큼만 사용 (Whisper 잉여 단어 드롭)
        # Whisper < Script: 마지막 Whisper 타임스탬프로 나머지 보간
        n = max(len(script_words), len(whisper_words))
        last_w = whisper_words[-1]
        for i in range(n):
            w = whisper_words[i] if i < len(whisper_words) else last_w
            text = script_words[i] if i < len(script_words) else None
            if text is None:
                break  # script 범위 초과 → 드롭
            aligned.append({"word": text, "start": w["start"], "end": w["end"]})
        return aligned

    # ── Case 2: LCS 앵커 정렬 + 보간 ────────────────────────────────────
    norm_script  = [_normalize_word(w) for w in script_words]
    norm_whisper = [_normalize_word(w["word"]) for w in whisper_words]

    anchors = _lcs_anchors(norm_script, norm_whisper)  # [(script_i, whisper_j), ...]

    t_total_start = whisper_words[0]["start"]
    t_total_end   = whisper_words[-1]["end"]

    # 앵커 없음 → 전체 균등 분배
    if not anchors:
        print(f"  [자막 정렬] LCS 앵커 0개 — 글자 수 비례 균등 분배 ({lang})")
        return _interpolate_segment(script_words, t_total_start, t_total_end)

    anchor_map: dict[int, tuple[float, float]] = {
        si: (whisper_words[wi]["start"], whisper_words[wi]["end"])
        for si, wi in anchors
    }
    anchor_indices = sorted(anchor_map.keys())

    result: list[dict] = []

    # 첫 앵커 이전
    first = anchor_indices[0]
    if first > 0:
        result.extend(_interpolate_segment(script_words[:first], t_total_start, anchor_map[first][0]))

    # 앵커 + 앵커 사이 구간
    for k, si in enumerate(anchor_indices):
        result.append({"word": script_words[si], "start": anchor_map[si][0], "end": anchor_map[si][1]})
        if k + 1 < len(anchor_indices):
            next_si = anchor_indices[k + 1]
            seg = _interpolate_segment(
                script_words[si + 1:next_si],
                anchor_map[si][1],
                anchor_map[next_si][0],
            )
            result.extend(seg)

    # 마지막 앵커 이후
    last = anchor_indices[-1]
    if last < len(script_words) - 1:
        result.extend(_interpolate_segment(script_words[last + 1:], anchor_map[last][1], t_total_end))

    matched_ratio = len(anchors) / len(script_words) * 100
    print(f"  [자막 정렬] LCS 앵커 {len(anchors)}/{len(script_words)}개 매칭 ({matched_ratio:.0f}%) — 나머지 보간 ({lang})")

    return result


def generate_word_timestamps(audio_path: str, api_key: str | None = None, language: str = "ko") -> list[dict]:
    """Whisper API로 단어 단위 타임스탬프 추출. 타임아웃/네트워크 오류 시 최대 2회 재시도."""
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
                print(f"[Whisper 경고] API 응답에 word timestamp가 없습니다 ({os.path.basename(audio_path)})")
            else:
                for w in raw_words:
                    try:
                        if isinstance(w, dict):
                            words.append({"word": str(w["word"]), "start": float(w["start"]), "end": float(w["end"])})
                        else:
                            words.append({"word": str(w.word), "start": float(w.start), "end": float(w.end)})
                    except Exception as parse_err:
                        print(f"[Whisper 경고] 단어 파싱 실패 (건너뜀): {parse_err}")
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
