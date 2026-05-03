---
name: channel-ending
description: 채널 엔딩 스타일러 — 채널별 루프/마무리 톤 분리 (구현 예정)
user_invocable: true
---

# /channel-ending — 채널 엔딩 스타일러

채널별 마지막 컷 스타일을 분리합니다.

## 상태: 구현 예정

## 목표
- askanything: 강한 루프 — 첫 문장과 거의 동일한 반복
- wonderdrop: 자연스러운 콜백 — 주제 연결
- exploratodo: 빠른 직접적 루프
- prismtale: 미스터리한 열린 결말

## 사용법
```
/channel-ending plan → 구현 계획 확인
```

## Expertise Harness

### 1. Role Contract
채널 엔딩 스타일러는 마지막 컷의 루프 강도와 감정 여운을 채널별로 분리하는 구조 전문가다.

### 2. Inputs
- first cut script, last cut script, channel, format_type
- channel tone and loop style from `channel_config.py`

### 3. Expert Judgment Criteria
- askanything/exploratodo는 직접적 반복과 강한 콜백.
- wonderdrop은 자연스러운 documentary callback.
- prismtale은 열린 미스터리지만 미완성 문장은 금지.

### 4. Hard Fail
- “다음에 알려줄게” 같은 빈 CTA.
- 마지막 컷이 문장으로 완결되지 않음.
- 채널 톤과 반대되는 과장/장난/건조함.

### 5. Auto-Fix Policy
- 마지막 컷 `script`만 수정한다.
- 컷1의 핵심 명사를 되살리되, 새 사실은 추가하지 않는다.
- 수정 후 `_validate_hard_fail()`의 LOOP 조건을 통과해야 한다.

### 6. Output Contract
- `ending_style`, `original_last`, `fixed_last`, `reason`

### 7. Code Wiring
- Planned: `modules/gpt/cutter/verifier.py`
- Current related logic: `_verify_highness_structure()`, `_validate_hard_fail()`

### 8. Verification Harness
- Good: prismtale은 여운 있는 완성 문장, exploratodo는 짧고 직접적인 콜백.
- Bad: 모든 채널에 같은 “다음 편에서” CTA 사용.
