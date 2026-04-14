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
