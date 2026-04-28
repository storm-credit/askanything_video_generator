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
