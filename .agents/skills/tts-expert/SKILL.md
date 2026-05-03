---
name: tts-expert
description: TTS 전문가 — 채널별 음성 설정 최적화, 보이스 A/B 테스트, TTS 엔진 전환
user_invocable: true
---

# /tts — TTS 전문가

YouTube Shorts 4채널 TTS 설정을 전문가 관점에서 관리합니다.

## 사용법

```
/tts status       → 현재 4채널 TTS 설정 확인
/tts optimize     → 전문가 기준 설정 최적화 제안
/tts test [채널]  → 특정 채널 음성 테스트 생성
/tts compare      → ElevenLabs vs Qwen3-TTS 비교
```

## 현재 설정 (코드 기준)

| 채널 | 엔진 | Voice | Speed | Style | 판정 |
|------|------|-------|-------|-------|------|
| askanything | Qwen3 우선, ElevenLabs fallback | eric / Eric | 1.3 | brisk Korean male | ✅ 빠른 한국어 운영 |
| wonderdrop | Qwen3 우선, ElevenLabs fallback | ryan / Adam | 1.05 | confident documentary | ✅ 안정 다큐 톤 |
| exploratodo | Qwen3 우선, ElevenLabs fallback | dylan / Daniel | 1.05 | energetic LATAM | ✅ 에너지형 |
| prismtale | Qwen3 우선, ElevenLabs fallback | dylan / Daniel | 1.05 | calm dark cinematic | ⚠️ voice_desc로 차별화 |

## 전문가 검증 기준 (2026-04-06 적용)

### 파라미터 규칙
- `stability`: 0.35~0.65 (낮을수록 감정 풍부, 높을수록 일관)
- `similarity_boost`: 0.80~0.85 (원본 충실도)
- `style`: 0.2~0.35 (0.5 이상 = 과장, 레이턴시 증가)
- `speed`: 언어별 최적값 — KO 1.0, EN 0.85, ES 0.9~1.0

### LUFS
- 타겟: -14.0 LUFS (YouTube/TikTok/Reels 표준)
- BGM+TTS 믹싱 후 재정규화 필요 여부 확인

### 대안 엔진 (미래)
- Qwen3-TTS: 무료, 품질 상, KO/EN/ES 지원, GPU 필요 (RTX 4070 Ti OK)
- Chatterbox: 무료, MIT, 23개 언어, 보이스 클론 5초
- 현재 ElevenLabs 유지 (월 $22, 안정적)

## 파일 위치
- 설정: `modules/utils/channel_config.py`
- TTS 코드: `modules/tts/elevenlabs.py`
- 오디오 정규화: `modules/utils/audio.py`

## Expertise Harness

### 1. Role Contract
TTS 전문가는 채널별 성우 톤, 속도, 감정 강도, 발음 안정성을 관리해 쇼츠가 답답하거나 어색하게 들리지 않게 한다.

### 2. Inputs
- `script`, `language`, `channel`, `emotion`, `tts_speed`
- `CHANNEL_VOICE_DESC`, `CHANNEL_SPEAKER`, `EMOTION_SPEED_FACTOR`
- `channel_config.py`의 `voice_id`, `voice_settings`, `tts_speed`

### 3. Expert Judgment Criteria
- 속도는 1.0 미만으로 내려가지 않는다.
- SHOCK/URGENCY/DISBELIEF만 빠른 감정 힌트를 붙이고, 나머지는 채널 앵커 톤을 유지한다.
- 한국어는 영문+숫자 토큰을 발음 가능하게 풀어쓴다. 예: `r5` → `알 오`.
- 반복 구절, 쉼표 뒤 유사 문장, 깨지는 기호 발음을 사전에 정리한다.

### 4. Hard Fail
- Qwen3 요청에 `channel`이 빠져 askanything voice_desc로 폴백.
- 감정 힌트에 slow, pause, whisper 등 속도 저하 단어 포함.
- `speed < 1.0`.
- 전처리 후 빈 문장인데 무음 fallback 없이 실패.
- Whisper timestamp가 원문과 정렬되지 않음.

### 5. Auto-Fix Policy
- alnum 토큰은 `prepare_spoken_script()`에서 발음형으로 정규화.
- Qwen3 실패 + ElevenLabs key 있음이면 fallback.
- TTS 생성 후 LUFS -14 dB 정규화.
- Whisper 실패 시 fallback word timestamps 생성.

### 6. Output Contract
- `ctx.audio_paths`: 컷 수와 같은 길이.
- `ctx.word_timestamps`: 컷 수와 같은 길이.
- `ctx.scripts`: TTS 전처리 후 스크립트와 동기화.

### 7. Code Wiring
- Runtime: `modules/orchestrator/agents/tts.py`
- Core: `modules/tts/elevenlabs.py`
- Alignment: `modules/transcription/whisper.py`
- Audio: `modules/utils/audio.py`

### 8. Verification Harness
- Good: `r5`, `NASA`, `3D` 같은 토큰이 언어별 발음 가능 형태로 변환.
- Bad: 채널 없이 Qwen3 호출되어 Spanish 채널이 Korean male desc를 사용.
- Regression target: 모든 TTS 호출 경로가 `channel`, `emotion`, `already_prepared`를 명시.
