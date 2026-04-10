---
name: jinhaeng
description: 오케스트라 채널×포맷 최적화 검증 + 적용. "진행" 입력 시 실행.
triggers:
  - "진행"
  - "오케스트라"
user_invocable: true
---

# /jinhaeng — 오케스트라 총괄 진행

"진행" 또는 "/jinhaeng" 입력 시 아래 순서로 실행.

## 에이전트 모델 분배 (고정 잠금)

| 에이전트 | 모델 | 역할 |
|---------|------|------|
| 총괄 오케스트라 | **Opus** | 판단, 종합, 의사결정, 코드 설계 |
| 파일 탐색/리서치 | **Sonnet** | Explore 에이전트, 코드 읽기·분석 |
| 코드 수정 실행 | **Sonnet** | 구체적 지시 기반 편집 |
| 간단한 확인/검색 | **Haiku** | grep, glob, 존재여부 확인 |
| 아키텍처 설계 | **Opus** | 복잡한 트레이드오프, 신규 시스템 설계 |

Agent 도구 호출 시 반드시 `model` 파라미터 명시:
```
- subagent_type: Explore → model: sonnet
- subagent_type: general-purpose (수정) → model: sonnet  
- subagent_type: Explore (확인) → model: haiku
- subagent_type: Plan (설계) → model: opus
```

## 하이네스 구조 실행 순서

### Phase 1 — 성과 분석가 (Haiku)
```
[성과 분석가] 채널별 현재 성과 데이터 로드
→ assets/_deploy_state.json 확인
→ 채널별 평균 완료율, 실패 패턴 분석
```

### Phase 2 — 스크립트 라이터 (Sonnet)
```
[스크립트 라이터] 포맷별 컷 구조 검증
→ formats/who_wins.py    — 11컷 구조 확인
→ formats/if_premise.py  — 10-11컷 구조 확인
→ formats/emotional_sci.py — 8-9컷 구조 확인
→ formats/fact.py        — 8-10컷 구조 확인
→ channel_config.py format_cuts 매핑 확인
```

### Phase 3 — 비주얼 디렉터 (Sonnet)
```
[비주얼 디렉터] 이미지 프롬프트 규칙 검증
→ _enhance_image_prompts format_type 전달 확인
→ WHO_WINS 컷1 좌우대칭 룰 확인
→ EMOTIONAL_SCI 따뜻한 색감 룰 확인
→ IF CLIMAX 극단 스케일 룰 확인
→ FACT 다큐멘터리 비주얼 룰 확인
```

### Phase 4 — 품질 게이트 (Sonnet)
```
[품질 게이트] HARD FAIL 조건 검증
→ cutter.py _validate_cuts() 포맷 검증 블록
→ WHO_WINS 11컷 필수 검증
→ EMOTIONAL_SCI 전체컷 SHOCK 금지
→ 확장 트리거 < _cfg_min 확인
```

### Phase 5 — TTS·자막 (Sonnet)
```
[TTS·자막] 감정 연출 검증
→ EMOTION_VOICE_DESC 합성 로직 확인
→ EMOTION_SPEED_FACTOR 배율 적용 확인
→ Main.tsx → Captions channel prop 전달 확인
```

### Phase 6 — 비용 관리자 (Haiku)
```
[비용 관리자] 포맷별 예상 비용 계산
→ WHO_WINS 11컷: Imagen 11장 + Veo3 2개(SHOCK+REVEAL)
→ IF 10컷: Imagen 10장 + Veo3 2개
→ EMOTIONAL_SCI 8컷: Imagen 8장 + Veo3 2개
→ FACT 9컷: Imagen 9장 + Veo3 2개
→ 일일 비용 추정
```

## 검증 실행 코드

```python
cd C:/ProjectS/askanything_video_generator
python -c "
from modules.gpt.prompts.formats import inject_format_prompt
from modules.utils.channel_config import CHANNEL_PRESETS

formats = ['WHO_WINS', 'IF', 'EMOTIONAL_SCI', 'FACT']
channels = ['askanything', 'wonderdrop', 'exploratodo', 'prismtale']
langs = {'askanything': 'ko', 'wonderdrop': 'en', 'exploratodo': 'es', 'prismtale': 'es'}

print('=== 채널×포맷 컷 수 매핑 ===')
for ch in channels:
    preset = CHANNEL_PRESETS[ch]
    fc = preset.get('format_cuts', {})
    lang = langs[ch]
    print(f'\n{ch} ({lang}, {preset[\"tts_speed\"]}x, 목표{preset[\"target_duration\"]}s)')
    for fmt in formats:
        cuts = fc.get(fmt, {})
        print(f'  {fmt:<16}: {cuts.get(\"min\",8)}-{cuts.get(\"max\",10)}컷')

print('\n=== 포맷 프롬프트 주입 테스트 ===')
for fmt in formats:
    for lang in ['ko', 'en', 'es']:
        result = inject_format_prompt('BASE', fmt, lang)
        ok = result != 'BASE'
        print(f'  {fmt} {lang}: {\"OK\" if ok else \"FAIL\"}')
"
```

## 보고 형식

```
[성과 분석가] ✅ 채널 4개 상태 확인 완료        (Haiku)
[스크립트 라이터] ✅ 포맷 프롬프트 4종 검증 완료  (Sonnet)
[비주얼 디렉터] ✅ 이미지 룰 확인 완료          (Sonnet)
[품질 게이트] ✅ HARD FAIL 조건 검증 완료       (Sonnet)
[TTS·자막] ✅ 감정 연출 검증 완료              (Sonnet)
[비용 관리자] ✅ 일일 예상 비용: ~$X            (Haiku)
─────────────────────────────
🎼 오케스트라 총괄: 진행 완료 ✅ (Opus)
```
