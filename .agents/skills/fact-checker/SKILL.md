---
name: fact-checker
description: 팩트 체커 — 조건부 팩트 검증, 고위험 포맷+키워드만 실행
user_invocable: true
---

# /fact-checker — 팩트 체커

고위험 주제만 선별적으로 팩트 검증합니다.

## 담당 파일
- `modules/gpt/cutter/verifier.py` → `_verify_facts()`
- `modules/gpt/cutter/generator.py` → `_should_run_fact_verify()`

## 호출 조건
- 고위험 포맷: FACT, PARADOX, MYSTERY, COUNTDOWN, EMOTIONAL_SCI
- 고위험 키워드: 연도(\d{4}), 퍼센트(\d+%), 연구/논문/과학자 등
- WHO_WINS, SCALE, IF: 위험 키워드 없으면 스킵

## 핵심 규칙
- RAG 팩트체크 컨텍스트 기반 검증
- 글자수 보호: 40%+ 감소 거부, 15자 미만 거부
- 톤/스타일/길이 유지하며 팩트만 수정

## 사용법
```
/fact-checker rules → 호출 조건 확인
```

## Expertise Harness

### 1. Role Contract
팩트 체커는 고위험 주제에서 조회수용 과장을 사실 오류로 넘기지 않게 막는 검증자다.

### 2. Inputs
- `cuts[].script`
- fact_context from Tavily/search/reference
- topic, format_type, language

### 3. Expert Judgment Criteria
- 검색 근거와 충돌하는 수치/연도/원인/최초/최대 표현을 우선 확인.
- 불확실한 주장은 단정형보다 완화 표현으로 바꾼다.
- 사실 수정 후에도 쇼츠 호흡과 길이를 유지한다.

### 4. Hard Fail
- fact_context와 정면 충돌하는 주장.
- 출처 없는 의료/건강 조언.
- 날짜/수치/인명/연구결과를 과장해 단정.
- 수정 결과가 원문 대비 40% 이상 짧아져 정보가 사라짐.

### 5. Auto-Fix Policy
- script만 수정한다.
- 같은 톤과 비슷한 길이를 유지한다.
- 15자 미만 또는 과도 축약 수정은 거부한다.

### 6. Output Contract
- JSON array: `cut`, `original`, `verified`, `changed`, `reason`
- 변경 컷 수와 거부 사유를 로그로 남긴다.

### 7. Code Wiring
- Core: `modules/gpt/cutter/verifier.py` → `_verify_facts()`
- Trigger: `modules/gpt/cutter/generator.py` → `_should_run_fact_verify()`

### 8. Verification Harness
- Good: 과학 수치를 근거에 맞게 조정하되 문장 리듬 유지.
- Bad: 안전하게 만들겠다며 훅/payoff를 삭제.
- Regression target: 고위험 키워드가 있을 때만 실행되고 저위험 WHO_WINS/SCALE은 스킵.
