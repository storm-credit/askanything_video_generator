"""오디오 정규화 유틸리티 — ITU-R BS.1770 / EBU R 128 기반 LUFS 정규화"""
import os
import subprocess
import tempfile


# YouTube/TikTok/Reels 권장 라우드니스 (-14 LUFS)
TARGET_LUFS = -14.0


def normalize_audio_lufs(audio_path: str, target_lufs: float = TARGET_LUFS) -> str:
    """오디오 파일을 target LUFS로 정규화합니다.

    pyloudnorm 사용 가능 시 정밀 정규화, 불가능 시 ffmpeg loudnorm 필터 사용.
    원본 파일을 정규화된 파일로 교체합니다.
    """
    if not audio_path or not os.path.exists(audio_path):
        return audio_path

    file_size = os.path.getsize(audio_path)
    if file_size == 0:
        return audio_path

    # pyloudnorm 시도 (정밀)
    try:
        return _normalize_pyloudnorm(audio_path, target_lufs)
    except ImportError:
        pass
    except Exception as e:
        print(f"[오디오 정규화] pyloudnorm 실패, ffmpeg 폴백: {e}")

    # ffmpeg 폴백
    try:
        return _normalize_ffmpeg(audio_path, target_lufs)
    except Exception as e:
        print(f"[오디오 정규화 경고] 정규화 건너뜀: {e}")
        return audio_path


def _normalize_pyloudnorm(audio_path: str, target_lufs: float) -> str:
    """pyloudnorm + soundfile 기반 정밀 LUFS 정규화"""
    import soundfile as sf
    import pyloudnorm as pyln

    data, rate = sf.read(audio_path)

    meter = pyln.Meter(rate)
    current_lufs = meter.integrated_loudness(data)

    # -70 LUFS 이하는 거의 무음 → 정규화 불필요
    if current_lufs < -70.0:
        return audio_path

    normalized = pyln.normalize.loudness(data, current_lufs, target_lufs)

    # 원본 확장자 유지하여 덮어쓰기
    ext = os.path.splitext(audio_path)[1].lower()
    if ext == ".mp3":
        # soundfile은 mp3 쓰기 미지원 → wav로 변환 후 ffmpeg로 mp3 재인코딩
        wav_path = audio_path.rsplit(".", 1)[0] + "_norm.wav"
        sf.write(wav_path, normalized, rate)
        _convert_wav_to_mp3(wav_path, audio_path)
        os.remove(wav_path)
    else:
        sf.write(audio_path, normalized, rate)

    delta = target_lufs - current_lufs
    print(f"   [LUFS] {current_lufs:.1f} → {target_lufs:.1f} LUFS (보정: {delta:+.1f}dB)")
    return audio_path


def _normalize_ffmpeg(audio_path: str, target_lufs: float) -> str:
    """ffmpeg loudnorm 필터 기반 LUFS 정규화 (2-pass)"""
    ext = os.path.splitext(audio_path)[1]
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=ext)
    os.close(tmp_fd)

    try:
        cmd = [
            "ffmpeg", "-y", "-i", audio_path,
            "-af", f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11",
            "-ar", "44100", tmp_path,
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        if result.returncode == 0 and os.path.getsize(tmp_path) > 0:
            os.replace(tmp_path, audio_path)
            print(f"   [LUFS] ffmpeg loudnorm → {target_lufs} LUFS")
            return audio_path
        else:
            raise RuntimeError(f"ffmpeg 실패: {result.stderr[:200]}")
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _convert_wav_to_mp3(wav_path: str, mp3_path: str) -> None:
    """WAV를 MP3로 변환 (ffmpeg 사용)"""
    cmd = [
        "ffmpeg", "-y", "-i", wav_path,
        "-codec:a", "libmp3lame", "-b:a", "192k", mp3_path,
    ]
    subprocess.run(
        cmd, capture_output=True, timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
