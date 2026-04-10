---
name: jinhaeng
description: 오케스트라 채널×포맷 최적화 검증 + 적용. "진행" 입력 시 실행.
triggers:
  - "진행"
user_invocable: true
---

# /jinhaeng — 오케스트라 채널×포맷 최적화 진행

"진행" 또는 "/jinhaeng" 입력 시 아래 오케스트라 에이전트 순서로 실행.

## 하이네스 구조 실행 순서

### Phase 1 — 성과 분석가 🔍
```
[성과 분석가] 채널별 현재 성과 데이터 로드
→ assets/_deploy_state.json 확인
→ 채널별 평균 완료율, 실패 패턴 분석
```

### Phase 2 — 스크립트 라이터 ✍️
```
[스크립트 라이터] 포맷별 컷 구조 검증
→ formats/who_wins.py    — 11컷 구조 확인
→ formats/if_premise.py  — 10-11컷 구조 확인
→ formats/emotional_sci.py — 8-9컷 구조 확인
→ channel_config.py format_cuts 매핑 확인
```

### Phase 3 — 비주얼 디렉터 🎬
```
[비주얼 디렉터] 이미지 프롬프트 규칙 검증
→ WHO_WINS 컷1 좌우대칭 룰 확인
→ EMOTIONAL_SCI 따뜻한 색감 룰 확인
→ IF CLIMAX 극단 스케일 룰 확인
```

### Phase 4 — 품질 게이트 ✅
```
[품질 게이트] HARD FAIL 조건 검증
→ cutter.py format_cuts 적용 로직 확인
→ 확장 트리거 임계값 (< 8) 확인
→ 채널별 min_cuts 매핑 테스트
```

### Phase 5 — 비용 관리자 💰
```
[비용 관리자] 포맷별 예상 비용 계산
→ WHO_WINS 11컷: Imagen 11장 + Veo3 2개(SHOCK+REVEAL)
→ IF 10컷: Imagen 10장 + Veo3 2개
→ EMOTIONAL_SCI 8컷: Imagen 8장 + Veo3 2개
→ 일일 비용 추정
```

## 실행 방법

```python
# 검증 실행
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
for fmt in formats[:3]:
    for lang in ['ko', 'en', 'es']:
        result = inject_format_prompt('BASE', fmt, lang)
        ok = result != 'BASE'
        print(f'  {fmt} {lang}: {\"OK\" if ok else \"FAIL\"}')
"
```

## 보고 형식

각 에이전트 실행 시 아래 로그 출력:
```
[성과 분석가] ✅ 채널 4개 상태 확인 완료
[스크립트 라이터] ✅ 포맷 프롬프트 3종 검증 완료
[비주얼 디렉터] ✅ 이미지 룰 확인 완료
[품질 게이트] ✅ HARD FAIL 조건 검증 완료
[비용 관리자] ✅ 일일 예상 비용: ~$X
─────────────────────────────
오케스트라 총괄: 진행 완료 ✅
```
