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

## 현재 설정 (channel_config.py)

| 채널 | 엔진 | Voice | Speed | Style | 판정 |
|------|------|-------|-------|-------|------|
| askanything | ElevenLabs | Eric | 1.0 | 0.35 | ✅ 전문가 검증 완료 |
| wonderdrop | ElevenLabs | Adam | 0.85 | 0.2 | ✅ 최적 |
| exploratodo | ElevenLabs | Daniel | 1.0 | 0.3 | ✅ 전문가 검증 완료 |
| prismtale | ElevenLabs | Daniel | 0.9 | 0.25 | ⚠️ LATAM/US 분리 권장 |

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
