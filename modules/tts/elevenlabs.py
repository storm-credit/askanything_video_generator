import os
import time
import struct
import random
import tempfile
import requests


MAX_RETRIES = 3


def _backoff_delay(attempt: int) -> float:
    """지수 백오프 + 지터 (AWS Architecture Blog: Exponential Backoff And Jitter)"""
    base = min(2 ** (attempt + 1), 16)  # 2, 4, 8, 16 cap
    return base + random.uniform(0, base * 0.5)


def _write_silent_wav(path: str, duration_sec: float = 1.0, sample_rate: int = 22050):
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


# ── 감정 태그 → Qwen3 voice_desc 매핑 ──
EMOTION_VOICE_DESC = {
    "SHOCK": "shocked, intense, urgent, breathless delivery",
    "WONDER": "amazed, full of wonder, slow and dramatic",
    "TENSION": "tense, suspenseful, building urgency, dark",
    "REVEAL": "dramatic reveal, confident, triumphant pause",
    "URGENCY": "urgent, pressing, time-critical, fast",
    "DISBELIEF": "incredulous, disbelief, questioning tone",
    "IDENTITY": "proud, personal, intimate warm connection",
    "CALM": "calm, reflective, gentle, soft delivery",
}

# ── 채널 → Qwen3 기본 voice_desc ──
CHANNEL_VOICE_DESC = {
    "askanything": "Deep Korean male voice, documentary narrator, curious and dramatic, emphasize numbers",
    "wonderdrop": "Deep calm male voice, cinematic documentary narrator, confident, Netflix documentary feel",
    "exploratodo": "Energetic young male voice, Latin American Spanish, excited and fast-paced, like a friend telling something incredible",
    "prismtale": "Deep male voice, neutral Spanish, dark cinematic tone, mysterious, slow controlled delivery",
}

QWEN3_TTS_URL = os.getenv("QWEN3_TTS_URL", "http://host.docker.internal:8010")


def _generate_qwen3(text: str, output_path: str, language: str = "ko",
                     voice_desc: str | None = None, emotion: str | None = None,
                     channel: str | None = None) -> str | None:
    """Qwen3-TTS HTTP API로 음성 생성."""
    # 채널별 기본 voice_desc
    base_desc = CHANNEL_VOICE_DESC.get(channel, CHANNEL_VOICE_DESC.get("askanything", ""))
    # 감정 태그 추가
    if emotion and emotion in EMOTION_VOICE_DESC:
        base_desc += f", {EMOTION_VOICE_DESC[emotion]}"
    # 사용자 지정 voice_desc 우선
    final_desc = voice_desc or base_desc

    try:
        import json
        resp = requests.post(
            f"{QWEN3_TTS_URL}/generate",
            json={"text": text, "engine": "qwen3", "lang": language, "voice_desc": final_desc},
            timeout=120,
        )
        if resp.status_code == 200 and len(resp.content) > 1000:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "wb") as f:
                f.write(resp.content)
            print(f"OK [Qwen3-TTS] 컷 음성 생성 완료! ({len(resp.content)//1024}KB)")
            return output_path
        else:
            error_msg = resp.text[:100] if resp.status_code != 200 else "too small"
            print(f"[Qwen3-TTS 실패] {resp.status_code}: {error_msg}")
            return None
    except Exception as e:
        print(f"[Qwen3-TTS 연결 실패] {e}")
        return None


def generate_tts(text: str, index: int, topic_folder: str, api_key_override: str = None, language: str = "ko", speed: float | None = None, voice_id: str | None = None, voice_settings: dict | None = None, emotion: str | None = None, channel: str | None = None) -> str | None:
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

    # TTS 엔진 선택: QWEN3 우선
    tts_engine = os.getenv("TTS_ENGINE", "qwen3").lower()

    if tts_engine == "qwen3":
        output_dir = os.path.join("assets", topic_folder, "audio")
        os.makedirs(output_dir, exist_ok=True)
        wav_path = os.path.join(output_dir, f"cut_{index:02d}.wav")

        result = _generate_qwen3(text, wav_path, language, emotion=emotion, channel=channel)
        if result:
            return result
        print(f"[TTS] Qwen3 실패 → ElevenLabs 폴백")

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

    # speed: 0.7(느리게) ~ 1.0(기본) ~ 1.2(빠르게), 숏폼은 0.85~0.9 권장
    tts_speed = speed if speed is not None else float(os.getenv("ELEVENLABS_SPEED", "0.9"))

    default_voice_settings = {
        "stability": 0.5,
        "similarity_boost": 0.75,
        "style": 0.0,
        "use_speaker_boost": True,
    }
    final_voice_settings = {**default_voice_settings, **(voice_settings or {})}

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
