---
name: polisher
description: 문장 폴리셔 — 채널별 톤 맞춤 자연화, 컷1 보존, skip_indices 관리
user_invocable: true
---

# /polisher — 문장 폴리셔

생성된 스크립트를 채널 톤에 맞게 자연스럽게 다듬습니다.

## 담당 파일
- `modules/gpt/cutter/enhancer.py` → `polish_scripts()`, `_get_sentence_polish_prompt()`

## 핵심 규칙
- 컷1(훅)은 skip_indices=[0]으로 제외 — 훅 임팩트 보존
- 채널별 톤: askanything=친근 반말, wonderdrop=다큐 권위, exploratodo=에너지, prismtale=미스터리
- 안전 검사: 길이 ±50% 초과 시 거부
- 정보 추가/삭제 금지, 한 컷 한 문장 유지

## 사용법
```
/polisher check   → 현재 채널별 프롬프트 확인
/polisher tune    → 톤 미세 조정
```

## Expertise Harness

### 1. Role Contract
문장 폴리셔는 정보를 바꾸지 않고 말맛, 호흡, 채널 톤만 다듬는다. 목표는 자연스러운 낭독감이며, 훅과 루프의 힘을 약화시키지 않는다.

### 2. Inputs
- `cuts[].script`, `language`, `channel`
- `forbidden_phrases`, pre-polish hook/mid/last snapshots
- `skip_indices`

### 3. Expert Judgment Criteria
- KO askanything은 친근한 반말, 짧은 호흡, 번역투 제거.
- wonderdrop은 calm documentary가 아니라 forward-driving authority.
- exploratodo는 에너지 있지만 과한 지역 slang 금지.
- prismtale은 차분하고 미스터리하지만 늘어지면 안 됨.

### 4. Hard Fail
- 컷 수 변경.
- 새 사실 추가 또는 원래 사실 삭제.
- 컷1 훅 약화 또는 불필요하게 길어짐.
- 마지막 컷이 미완성 문장이나 빈 CTA로 바뀜.
- 금지 표현 재삽입.

### 5. Auto-Fix Policy
- 컷1은 기본적으로 skip한다.
- 컷4와 마지막 컷은 길이가 1.3배 이상 늘면 원본 복원.
- 안전 검사 실패 문장은 원본 유지.
- 금지 표현은 polish 전/후 모두 필터링.

### 6. Output Contract
- 같은 길이의 `cuts` 배열.
- 변경 대상은 `script` 필드만.
- `notes`에는 적용/거부/복원 이유를 짧게 기록.

### 7. Code Wiring
- Core: `modules/gpt/cutter/enhancer.py` → `polish_scripts()`
- Runtime: `modules/orchestrator/agents/polish.py`
- Final gate: `modules/gpt/cutter/quality.py` → `_validate_hard_fail()`

### 8. Verification Harness
- Good: 딱딱한 문어체를 짧은 구어체로 바꾸지만 정보는 그대로.
- Bad: 강한 훅을 평범한 설명문으로 완화.
- Regression target: `skip_indices=[0]`가 v1/v2 모두 적용되는지 검사.
