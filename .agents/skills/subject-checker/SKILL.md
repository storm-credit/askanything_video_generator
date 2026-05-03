---
name: subject-checker
description: 주제 일치 검증 — script↔image_prompt 피사체 매칭, LLM 기반 자동 수정
user_invocable: true
---

# /subject-checker — 주제 일치 검증

스크립트의 주제와 이미지 프롬프트의 피사체가 일치하는지 검증합니다.

## 담당 파일
- `modules/gpt/cutter/verifier.py` → `_verify_subject_match()`

## 핵심 규칙
- MISMATCH: 상어 script에 고래 image → 자동 수정
- MATCH: 상어 script에 백상아리 image → 허용 (관련 맥락 OK)
- 비주얼 디렉터 후 재검증 (무관 피사체 방지)
- 구조 수정으로 스크립트 변경 시 재검증 1회

## 사용법
```
/subject-checker status → 검증 통과율 확인
```

## Expertise Harness

### 1. Role Contract
주제 일치 검증자는 script와 image_prompt의 중심 피사체가 같은지 확인하고, 시각 피사체 이탈을 막는다.

### 2. Inputs
- `cuts[].script`, `cuts[].prompt`
- topic title, format_type, channel

### 3. Expert Judgment Criteria
- 동일 종/동일 물체/동일 현상은 match.
- 상위/하위 개념은 문맥상 자연스러우면 match.
- 전혀 다른 피사체, 임의 공룡/상어/우주 배경 삽입은 mismatch.

### 4. Hard Fail
- script가 A를 말하는데 image_prompt가 B를 보여줌.
- WHO_WINS의 A/B 이름이 중간에 바뀜.
- visual director 후 피사체가 새로 이탈함.

### 5. Auto-Fix Policy
- 수정 대상은 `prompt`만.
- script는 변경하지 않는다.
- 수정 prompt는 영어, 9:16, no text 규칙을 유지한다.

### 6. Output Contract
- 같은 길이의 `cuts` 배열.
- mismatch 컷만 `fixed_prompt`를 적용.

### 7. Code Wiring
- Core: `modules/gpt/cutter/verifier.py` → `_verify_subject_match()`
- Runtime: `modules/orchestrator/agents/quality.py`, `visual.py`

### 8. Verification Harness
- Good: “shark” script와 “great white shark” image는 match.
- Bad: “brain” script와 “galaxy background” image는 mismatch.
- Regression target: visual rewrite 전/후 subject checker가 같은 topic anchor를 사용.
