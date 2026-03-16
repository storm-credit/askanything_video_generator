import os
import time
import struct
import random
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


def generate_tts(text: str, index: int, topic_folder: str, api_key_override: str = None, language: str = "ko", speed: float | None = None, voice_id: str | None = None) -> str | None:
    """
    ElevenLabs API를 사용하여 매우 사실적인 다큐멘터리/쇼츠용 음성(.mp3)을 생성합니다.
    빈 텍스트 → 기본 문구로 대체, 타임아웃/네트워크 오류 → 최대 3회 재시도.
    eleven_multilingual_v2 모델이 텍스트 언어를 자동 감지하므로 별도 언어 설정 불필요.
    """
    # 빈 스크립트: 1초 무음 WAV 생성 (API 호출 절약)
    if not text or not text.strip() or text.strip() == "...":
        print(f"[ElevenLabs 경고] 컷 {index+1} 스크립트가 비어 있어 무음 오디오를 생성합니다.")
        output_dir = os.path.join("assets", topic_folder, "audio")
        os.makedirs(output_dir, exist_ok=True)
        silent_path = os.path.join(output_dir, f"cut_{index:02d}.wav")
        _write_silent_wav(silent_path, duration_sec=1.0)
        return silent_path

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

    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
        },
        "speed": tts_speed,
    }

    output_dir = os.path.join("assets", topic_folder, "audio")
    os.makedirs(output_dir, exist_ok=True)
    audio_path = os.path.join(output_dir, f"cut_{index:02d}.mp3")

    for attempt in range(MAX_RETRIES):
        try:
            label = f"(시도 {attempt+1}/{MAX_RETRIES})" if attempt > 0 else ""
            lang_label = "EN" if language == "en" else "KO"
            print(f"-> [초호화 성우 엔진 (ElevenLabs)] 컷 {index+1} 내레이션 렌더링 중... [{lang_label}] {label}")

            response = requests.post(URL, json=data, headers=headers, timeout=30, stream=True)

            if response.status_code == 200:
                with open(audio_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=4096):
                        if chunk:
                            f.write(chunk)
                if os.path.getsize(audio_path) == 0:
                    print(f"[ElevenLabs 오류] 컷 {index+1} 음성 파일이 비어 있습니다.")
                    try:
                        os.remove(audio_path)
                    except OSError:
                        pass
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(_backoff_delay(attempt))
                        continue
                    return None
                print(f"OK [초호화 성우 엔진 (ElevenLabs)] 컷 {index+1} 음성 생성 완료!")
                return audio_path

            elif response.status_code == 401:
                # 인증 오류는 재시도 무의미
                print("[ElevenLabs 인증 오류] API Key가 유효하지 않습니다. .env 파일을 확인하세요.")
                return None

            elif response.status_code == 429:
                # 할당량 초과: 대기 후 재시도
                wait = _backoff_delay(attempt)
                print(f"[ElevenLabs 할당량 초과] {wait}초 후 재시도... ({attempt+1}/{MAX_RETRIES})")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(wait)
                    continue
                print("[ElevenLabs 할당량 초과] 최대 재시도 횟수 도달. API 요금제를 확인하세요.")
                return None

            else:
                print(f"[ElevenLabs 오류] 요청 실패 ({response.status_code}): {response.text[:200]}")
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
