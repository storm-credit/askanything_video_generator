---
name: format-test
description: 포맷 시스템(WHO_WINS/IF/EMOTIONAL_SCI/FACT) 실전 검증
user_invocable: true
---

# /format-test — 포맷 시스템 실전 테스트

4개 포맷의 프롬프트 주입, 컷 수 매핑, 검증 규칙을 테스트합니다.

## 테스트 항목

1. **프롬프트 주입**: 4포맷 × 3언어 = 12개 조합 모두 OK인지
2. **컷 수 범위**: 포맷별 min/max가 channel_config과 일치하는지
3. **검증 규칙**: WHO_WINS 11컷, EMOTIONAL_SCI SHOCK 금지 등 _validate_cuts 점검
4. **폴백 체인**: detect_format_type 키워드 감지 + preferred_formats 동작 확인
5. **이미지 전략**: _enhance_image_prompts에 format_type 전달 경로 확인

## 실행 방법

```bash
cd C:/ProjectS/askanything_video_generator
python -c "
from modules.gpt.prompts.formats import inject_format_prompt, detect_format_type, get_format_cut_override
from modules.utils.channel_config import CHANNEL_PRESETS

# 1. 프롬프트 주입 테스트
print('=== 프롬프트 주입 ===')
for fmt in ['WHO_WINS', 'IF', 'EMOTIONAL_SCI', 'FACT']:
    for lang in ['ko', 'en', 'es']:
        r = inject_format_prompt('BASE', fmt, lang)
        ok = r != 'BASE'
        print(f'  {fmt:16} {lang}: {\"OK\" if ok else \"FAIL\"} ({len(r)-4}자)')

# 2. 키워드 감지 테스트
print('\n=== 키워드 감지 ===')
tests = [
    ('호랑이 vs 사자', 'ko', 'WHO_WINS'),
    ('만약 지구에서 물이 사라진다면', 'ko', 'IF'),
    ('tiger vs lion', 'en', 'WHO_WINS'),
    ('what if gravity disappeared', 'en', 'IF'),
    ('일반 주제 테스트', 'ko', None),
]
for topic, lang, expected in tests:
    result = detect_format_type(topic, lang)
    ok = result == expected
    print(f'  {topic[:30]:30} → {str(result):16} (기대: {expected}) {\"OK\" if ok else \"FAIL\"} ')

# 3. 컷 수 오버라이드 테스트
print('\n=== 컷 수 오버라이드 ===')
for fmt in ['WHO_WINS', 'IF', 'EMOTIONAL_SCI', 'FACT']:
    mn, mx = get_format_cut_override(fmt, 8, 10)
    print(f'  {fmt:16}: {mn}~{mx}컷')
"
```
