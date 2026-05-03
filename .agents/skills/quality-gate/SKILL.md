---
name: quality-gate
description: 품질 게이트 — HARD FAIL 코드 검증, 포맷 뼈대, warning 분리
user_invocable: true
---

# /quality-gate — 품질 게이트

LLM 없이 코드 레벨로 품질을 검증합니다.

## 담당 파일
- `modules/gpt/cutter/quality.py` → `_validate_hard_fail()`, `_validate_narrative_arc()`, `_validate_region_style()`

## HARD FAIL (즉시 실패)
- HOOK_WEAK, LOOP_INCOMPLETE, LOOP_CTA, LOOP_MISSING
- VISUAL_WEAK, ACADEMIC_TONE, CONTENT_REPEAT
- 포맷 뼈대: WHO_WINS 11컷, REVEAL 위치, EMOTIONAL_SCI SHOCK 금지
- IF CHAIN 0개, PARADOX 반전 0개

## SOFT GUARD (경고만)
- HOOK_TOO_LONG, EMOTION_REPEAT, TENSION_FLAT, TONE_MISMATCH
- 포맷별 컷1 감정태그, 수치밀도, 반전횟수 (_SOFT)

## 사용법
```
/quality-gate rules  → HARD FAIL vs SOFT GUARD 목록
/quality-gate stats  → 최근 배치 통과율
```

## Expertise Harness

### 1. Role Contract
품질 게이트는 LLM 취향 평가가 아니라 코드 레벨로 실패 조건을 막는 최종 심판이다.

### 2. Inputs
- `cuts[].script`, `cuts[].description`, `cuts[].prompt`
- `channel`, `format_type`, topic metadata

### 3. Expert Judgment Criteria
- 하드 실패는 렌더 중단 또는 재작성 대상.
- 소프트 가드는 warning으로 남겨 다음 튜닝에 사용.
- 프롬프트에 적힌 HARD FAIL과 코드 검증은 최대한 일치해야 한다.

### 4. Hard Fail
- HOOK_WEAK, LOOP_INCOMPLETE, LOOP_CTA, LOOP_MISSING.
- VISUAL_WEAK, ACADEMIC_TONE, CONTENT_REPEAT.
- 포맷 뼈대 붕괴: WHO_WINS 11컷, EMOTIONAL_SCI SHOCK 금지, IF chain 없음, PARADOX 반전 없음.

### 5. Auto-Fix Policy
- 품질 게이트 자체는 수정하지 않는다.
- 수정은 Script/Structure/Polisher/VisualDirector 쪽으로 돌린다.
- 최종 gate에서 실패하면 렌더를 중단한다.

### 6. Output Contract
- `hard_fails: list[str]`
- `region_warnings: list[str]`
- 최종 오케스트라에서는 ERROR/WARN SSE로 노출.

### 7. Code Wiring
- Core: `modules/gpt/cutter/quality.py`
- Runtime: `modules/orchestrator/agents/quality.py`
- Final gate: `modules/orchestrator/orchestrator.py`

### 8. Verification Harness
- Good: 실패와 warning이 분리되어 렌더 중단 기준이 명확함.
- Bad: prompt에는 HARD FAIL인데 code는 warning만 발생.
- Regression target: format prompt HARD FAIL과 `_validate_hard_fail()` parity test.
