import os
import time
import struct
import random
import tempfile
import re
import requests
from difflib import SequenceMatcher


MAX_RETRIES = 3


def _backoff_delay(attempt: int) -> float:
    """지수 백오프 + 지터 (AWS Architecture Blog: Exponential Backoff And Jitter)"""
    base = min(2 ** (attempt + 1), 16)  # 2, 4, 8, 16 cap
    return base + random.uniform(0, base * 0.5)


def _write_silent_wav(path: str, duration_sec: float = 1.0, sample_rate: int = 24000):
    """무음 WAV 파일을 생성합니다 (API 호출 없이 빈 스크립트 처리용)."""
    num_samples = int(sample_rate * duration_sec)
    data_size = num_samples * 2  # 16-bit mono
    with open(path, "wb") as f:
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + data_size))
        f.write(b"WAVEfmt ")
        f.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16))
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(b"\x00" * data_size)


def _sanitize_tts_text(text: str, language: str = "ko") -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return cleaned
    replacements = {
        "—": ", ",
        "–": ", ",
        "…": "... ",
        "·": " ",
        "_": " ",
    }
    for src, dst in replacements.items():
        cleaned = cleaned.replace(src, dst)
    cleaned = " ".join(cleaned.split())
    return cleaned


_KO_ALPHA = {
    "a": "에이", "b": "비", "c": "씨", "d": "디", "e": "이", "f": "에프", "g": "지", "h": "에이치",
    "i": "아이", "j": "제이", "k": "케이", "l": "엘", "m": "엠", "n": "엔", "o": "오", "p": "피",
    "q": "큐", "r": "알", "s": "에스", "t": "티", "u": "유", "v": "브이", "w": "더블유", "x": "엑스",
    "y": "와이", "z": "지",
}
_KO_DIGIT = {
    "0": "제로", "1": "원", "2": "투", "3": "쓰리", "4": "포",
    "5": "파이브", "6": "식스", "7": "세븐", "8": "에이트", "9": "나인",
}
_EN_DIGIT = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
}


def _normalize_alnum_for_tts(text: str, language: str = "ko") -> str:
    def repl(match: re.Match[str]) -> str:
        token = match.group(0)
        if language == "ko":
            parts = []
            for ch in token:
                if ch.isalpha():
                    parts.append(_KO_ALPHA.get(ch.lower(), ch))
                elif ch.isdigit():
                    parts.append(_KO_DIGIT.get(ch, ch))
                else:
                    parts.append(ch)
            return " ".join(parts)
        return " ".join(token)

    return re.sub(r"\b[A-Za-z]{1,3}\d{1,3}\b", repl, text)


def _normalize_clause(text: str) -> str:
    text = re.sub(r"[^\w\s가-힣]", " ", (text or "").lower())
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _dedupe_adjacent_clauses(text: str) -> str:
    if "," not in text:
        return text

    clauses = [chunk.strip() for chunk in re.split(r"\s*,\s*", text) if chunk.strip()]
    if len(clauses) <= 1:
        return text

    kept: list[str] = []
    prev_norm = ""
    for clause in clauses:
        norm = _normalize_clause(clause)
        if not norm:
            continue
        if prev_norm:
            prev_tokens = prev_norm.split()
            curr_tokens = norm.split()
            shared_opening = 0
            for left, right in zip(prev_tokens, curr_tokens):
                if left != right:
                    break
                shared_opening += 1
            shared_tokens = set(prev_tokens) & set(curr_tokens)
            ratio = SequenceMatcher(None, prev_norm, norm).ratio()
            if (
                ratio >= 0.78
                or prev_norm in norm
                or norm in prev_norm
                or (shared_opening >= 2 and len(shared_tokens) >= 2)
            ):
                continue
        kept.append(clause)
        prev_norm = norm
    return ", ".join(kept) if kept else text


def _collapse_repeated_words(text: str) -> str:
    text = re.sub(r"\b([A-Za-z]{2,})\s+\1\b", r"\1", text, flags=re.IGNORECASE)
    text = re.sub(r"([가-힣]{2,})\s+\1", r"\1", text)
    return text


def prepare_spoken_script(text: str, language: str = "ko") -> str:
    cleaned = _sanitize_tts_text(text, language)
    if not cleaned:
        return cleaned
    cleaned = _normalize_alnum_for_tts(cleaned, language)
    cleaned = _dedupe_adjacent_clauses(cleaned)
    cleaned = _collapse_repeated_words(cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" ,")
    return cleaned


def check_quota(api_key: str = None) -> dict | None:
    """ElevenLabs 구독 정보를 조회하여 잔여 크레딧을 반환합니다."""
    key = api_key or os.getenv("ELEVENLABS_API_KEY")
    if not key or key == "YOUR_ELEVENLABS_API_KEY_HERE":
        return None
    try:
        resp = requests.get(
            "https://api.elevenlabs.io/v1/user/subscription",
            headers={"xi-api-key": key},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            used = data.get("character_count", 0)
            limit = data.get("character_limit", 0)
            remaining = max(0, limit - used)
            return {"used": used, "limit": limit, "remaining": remaining}
    except Exception as e:
        print(f"[ElevenLabs 경고] 쿼터 조회 실패: {e}")
    return None


# ── 감정 태그 → Qwen3 voice_desc 매핑 (2단계: FAST vs NORMAL) ──
# FAST 감정만 힌트 추가, 나머지는 채널 앵커만 사용 → 톤 일관성 확보
_FAST_HINT = "intense punchy delivery"
EMOTION_VOICE_DESC = {
    "SHOCK": _FAST_HINT,
    "URGENCY": _FAST_HINT,
    "DISBELIEF": _FAST_HINT,
}

# ── 채널 → Qwen3 기본 voice_desc ──
CHANNEL_VOICE_DESC = {
    "askanything": "Korean male, brisk short-form narration, tight rhythm, clean phrase endings, continuous energy throughout",
    "wonderdrop": "English male, confident steady narration, same energy throughout",
    "exploratodo": "Spanish male, energetic steady narration, same energy throughout",
    "prismtale": "Spanish male, calm steady narration, same energy throughout",
}

# ── 감정 태그 → TTS speed 배율 (채널 기본 speed에 곱함) ──
# 채널 기본 speed (예: 1.3) × 감정 배율 → 최종 speed
# 최소 1.00, 최대 1.50 클램프
# 2단계 speed: FAST(긴박 감정) vs NORMAL(나머지) — 미세 차이 제거로 톤 일관성 확보
_FAST_EMOTIONS = frozenset({"SHOCK", "URGENCY", "DISBELIEF"})
EMOTION_SPEED_FACTOR: dict[str, float] = {e: 1.10 for e in _FAST_EMOTIONS}
# NORMAL 감정은 기본 1.00 (dict에 없으면 .get(emotion, 1.0)으로 폴백)

QWEN3_TTS_URL = os.getenv("QWEN3_TTS_URL", "http://localhost:8010")


def _candidate_qwen3_urls() -> list[str]:
    """환경별로 시도할 Qwen3-TTS base URL 목록."""
    candidates = [
        QWEN3_TTS_URL,
        "http://localhost:8010",
        "http://host.docker.internal:8010",
        "http://tts:8010",
    ]
    seen: set[str] = set()
    normalized: list[str] = []
    for raw in candidates:
        url = (raw or "").strip().rstrip("/")
        if not url or url in seen:
            continue
        seen.add(url)
        normalized.append(url)
    return normalized

# ── 감정 태그 → ElevenLabs voice_settings 매핑 (2단계: FAST vs 채널기본) ──
_EL_FAST = {"stability": 0.30, "style": 0.45}
EMOTION_TO_EL_SETTINGS = {
    "SHOCK": _EL_FAST,
    "URGENCY": _EL_FAST,
    "DISBELIEF": _EL_FAST,
}


# ── 채널 → Qwen3 speaker 매핑 (채널별 다른 남성 음색) ──
CHANNEL_SPEAKER = {
    "askanything": "eric",      # 한국어 남성 — 깨끗하고 자연스러운 음색
    "wonderdrop": "ryan",       # 영어 남성 — 밝은 미국 남성, 깨끗한 중음
    "exploratodo": "dylan",     # 스페인어 LATAM — 활기찬 리듬감 있는 남성
    "prismtale": "dylan",       # 스페인어 US — 남성 앵커 유지, calm/dark voice_desc로 차별화
}


def _generate_qwen3(text: str, output_path: str, language: str = "ko",
                     voice_desc: str | None = None, emotion: str | None = None,
                     channel: str | None = None, speed: float | None = None) -> str | None:
    """Qwen3-TTS HTTP API로 음성 생성."""
    # 채널 기본 voice_desc
    base_desc = CHANNEL_VOICE_DESC.get(channel, CHANNEL_VOICE_DESC.get("askanything", ""))
    # 감정 2단계: FAST(SHOCK/URGENCY/DISBELIEF) → 힌트 추가, 나머지 → 채널 앵커만
    if voice_desc:
        final_desc = voice_desc
    elif emotion and emotion in EMOTION_VOICE_DESC:
        final_desc = f"{base_desc}, with {EMOTION_VOICE_DESC[emotion]}"
    else:
        final_desc = base_desc

    # 채널별 speaker 선택 — 미지원 speaker 폴백
    speaker = CHANNEL_SPEAKER.get(channel, "eric")
    _VALID_SPEAKERS = {"eric", "ryan", "dylan", "serena", "adam", "bella"}
    if speaker not in _VALID_SPEAKERS:
        print(f"  [Qwen3-TTS 경고] 미지원 speaker '{speaker}' → 'eric' 폴백")
        speaker = "eric"

    payload = {
        "text": text,
        "engine": "qwen3",
        "lang": language,
        "voice_desc": final_desc,
        "voice": speaker,
        **({"speed": speed} if speed else {}),
    }

    for base_url in _candidate_qwen3_urls():
        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.post(
                    f"{base_url}/generate",
                    json=payload,
                    timeout=(8, 120),
                )
                if resp.status_code == 200 and len(resp.content) > 1000:
                    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
                    with open(output_path, "wb") as f:
                        f.write(resp.content)
                    print(f"OK [Qwen3-TTS] 컷 음성 생성 완료! ({len(resp.content)//1024}KB) via {base_url}")
                    return output_path
                error_msg = resp.text[:100] if resp.status_code != 200 else "too small"
                print(f"[Qwen3-TTS 실패] {resp.status_code}: {error_msg} @ {base_url} (시도 {attempt+1}/{MAX_RETRIES})")
            except Exception as e:
                print(f"[Qwen3-TTS 연결 실패] {e} @ {base_url} (시도 {attempt+1}/{MAX_RETRIES})")

            if attempt < MAX_RETRIES - 1:
                wait = 2 ** (attempt + 1)
                print(f"  [Qwen3-TTS] {wait}초 후 재시도...")
                time.sleep(wait)
        print(f"  [Qwen3-TTS] 다음 URL로 전환: {base_url}")

    return None


def generate_tts(text: str, index: int, topic_folder: str, api_key_override: str = None, language: str = "ko", speed: float | None = None, voice_id: str | None = None, voice_settings: dict | None = None, emotion: str | None = None, channel: str | None = None, already_prepared: bool = False) -> str | None:
    """
    TTS 음성 생성. Qwen3-TTS 우선, 실패 시 ElevenLabs 폴백.
    """
    # 빈 스크립트: 1초 무음 WAV 생성
    if not text or not text.strip() or text.strip() == "...":
        print(f"[TTS 경고] 컷 {index+1} 스크립트가 비어 있어 무음 오디오를 생성합니다.")
        output_dir = os.path.join("assets", topic_folder, "audio")
        os.makedirs(output_dir, exist_ok=True)
        silent_path = os.path.join(output_dir, f"cut_{index:02d}.wav")
        _write_silent_wav(silent_path, duration_sec=1.0)
        return silent_path

    if not already_prepared:
        text = prepare_spoken_script(text, language)
    if not text or not text.strip() or text.strip() == "...":
        print(f"[TTS 경고] 컷 {index+1} 전처리 후 스크립트가 비어 있어 무음 오디오를 생성합니다.")
        output_dir = os.path.join("assets", topic_folder, "audio")
        os.makedirs(output_dir, exist_ok=True)
        silent_path = os.path.join(output_dir, f"cut_{index:02d}.wav")
        _write_silent_wav(silent_path, duration_sec=1.0)
        return silent_path

    # speed 미지정 시 channel_config에서 자동 로드
    if speed is None and channel:
        from modules.utils.channel_config import get_channel_preset
        _preset = get_channel_preset(channel)
        if _preset:
            speed = _preset.get("tts_speed")

    # speed 폴백: channel도 없으면 기본 1.0 (감정 배율 적용을 위해)
    if speed is None:
        speed = 1.0
    try:
        if float(speed) < 1.0:
            print(f"  [TTS speed] 요청 속도 {float(speed):.2f}x → 1.00x (느려짐 방지)")
            speed = 1.0
    except Exception:
        speed = 1.0

    # 감정 태그 → speed 배율 적용 (채널 기본값에 곱함)
    if emotion and emotion in EMOTION_SPEED_FACTOR:
        factor = EMOTION_SPEED_FACTOR[emotion]
        adjusted = round(speed * factor, 3)
        adjusted = max(1.00, min(1.50, adjusted))  # 클램프: 쇼츠 기본 속도 아래로 내리지 않음
        if adjusted != speed:
            print(f"  [TTS speed] {emotion} 배율 {factor} → {speed:.2f}x → {adjusted:.2f}x")
        speed = adjusted

    # TTS 엔진 선택: QWEN3 우선
    tts_engine = os.getenv("TTS_ENGINE", "qwen3").lower()

    if tts_engine == "qwen3":
        output_dir = os.path.join("assets", topic_folder, "audio")
        os.makedirs(output_dir, exist_ok=True)
        wav_path = os.path.join(output_dir, f"cut_{index:02d}.wav")

        result = _generate_qwen3(text, wav_path, language, emotion=emotion, channel=channel, speed=speed)
        if result:
            return result
        # Qwen3 실패 → ElevenLabs 폴백 시도 (키 있을 때만)
        _el_key = api_key_override or os.getenv("ELEVENLABS_API_KEY", "")
        if not _el_key or _el_key == "YOUR_ELEVENLABS_API_KEY_HERE":
            print(f"[TTS] Qwen3 실패 + ElevenLabs 키 없음 → TTS 불가")
            return None
        print(f"[TTS] Qwen3 실패 → ElevenLabs 폴백 시도")

    api_key = api_key_override or os.getenv("ELEVENLABS_API_KEY")
    if not api_key or api_key == "YOUR_ELEVENLABS_API_KEY_HERE":
        print("[ElevenLabs 오류] ELEVENLABS_API_KEY가 설정되지 않았습니다. .env 파일을 확인하세요.")
        return None

    final_voice_id = voice_id or os.getenv("ELEVENLABS_VOICE_ID", "cjVigY5qzO86Huf0OWal")  # 기본: Eric
    URL = f"https://api.elevenlabs.io/v1/text-to-speech/{final_voice_id}"

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key
    }

    # speed: 1.0(기본) ~ 1.2(빠르게). 기본은 숏폼용으로 느려지지 않게 1.05.
    tts_speed = speed if speed is not None else float(os.getenv("ELEVENLABS_SPEED", "1.05"))

    default_voice_settings = {
        "stability": 0.5,
        "similarity_boost": 0.75,
        "style": 0.0,
        "use_speaker_boost": True,
    }
    final_voice_settings = {**default_voice_settings, **(voice_settings or {})}

    # 감정 태그 → ElevenLabs voice_settings 동적 반영
    if emotion and emotion in EMOTION_TO_EL_SETTINGS:
        final_voice_settings.update(EMOTION_TO_EL_SETTINGS[emotion])
        print(f"  [ElevenLabs] 감정 반영: {emotion} → stability={final_voice_settings['stability']}, style={final_voice_settings['style']}")

    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": final_voice_settings,
        "speed": tts_speed,
    }

    output_dir = os.path.join("assets", topic_folder, "audio")
    os.makedirs(output_dir, exist_ok=True)
    audio_path = os.path.join(output_dir, f"cut_{index:02d}.mp3")

    for attempt in range(MAX_RETRIES):
        try:
            label = f"(시도 {attempt+1}/{MAX_RETRIES})" if attempt > 0 else ""
            lang_label = language.upper() if language else "KO"
            print(f"-> [초호화 성우 엔진 (ElevenLabs)] 컷 {index+1} 내레이션 렌더링 중... [{lang_label}] {label}")

            response = requests.post(URL, json=data, headers=headers, timeout=30, stream=True)

            if response.status_code == 200:
                tmp_path = None
                try:
                    fd, tmp_path = tempfile.mkstemp(dir=output_dir, suffix=".tmp")
                    os.close(fd)
                    with open(tmp_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=4096):
                            if chunk:
                                f.write(chunk)
                    if os.path.getsize(tmp_path) == 0:
                        print(f"[ElevenLabs 오류] 컷 {index+1} 음성 파일이 비어 있습니다.")
                        try:
                            os.remove(tmp_path)
                        except OSError:
                            pass
                        if attempt < MAX_RETRIES - 1:
                            time.sleep(_backoff_delay(attempt))
                            continue
                        return None
                    os.replace(tmp_path, audio_path)
                    tmp_path = None  # 성공 — 정리 불필요
                except Exception as write_exc:
                    response.close()
                    print(f"[ElevenLabs 오류] 컷 {index+1} 파일 쓰기 실패: {write_exc}")
                    if tmp_path:
                        try:
                            os.remove(tmp_path)
                        except OSError:
                            pass
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(_backoff_delay(attempt))
                        continue
                    return None
                # LUFS 정규화는 호출자(TTSAgent/generate.py)에서 단일 지점으로 처리
                print(f"OK [초호화 성우 엔진 (ElevenLabs)] 컷 {index+1} 음성 생성 완료!")
                return audio_path

            elif response.status_code == 401:
                response.close()
                print("[ElevenLabs 인증 오류] API Key가 유효하지 않습니다. .env 파일을 확인하세요.")
                return None

            elif response.status_code == 429:
                response.close()
                wait = _backoff_delay(attempt)
                print(f"[ElevenLabs 할당량 초과] {wait}초 후 재시도... ({attempt+1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(wait)
                    continue
                print("[ElevenLabs 할당량 초과] 최대 재시도 횟수 도달. API 요금제를 확인하세요.")
                return None

            else:
                response.close()
                print(f"[ElevenLabs 오류] 요청 실패 ({response.status_code})")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(_backoff_delay(attempt))
                    continue
                return None

        except requests.exceptions.Timeout:
            print(f"[ElevenLabs 타임아웃] 컷 {index+1} 응답 시간 초과 ({attempt+1}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES - 1:
                time.sleep(_backoff_delay(attempt))
                continue
            return None

        except requests.exceptions.ConnectionError:
            print(f"[ElevenLabs 연결 오류] 컷 {index+1} 서버 연결 실패 ({attempt+1}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES - 1:
                time.sleep(_backoff_delay(attempt))
                continue
            return None

        except Exception as e:
            print(f"[ElevenLabs 통신 오류] 컷 {index+1}: {e} ({attempt+1}/{MAX_RETRIES})")
            if attempt < MAX_RETRIES - 1:
                time.sleep(_backoff_delay(attempt))
                continue
            return None
