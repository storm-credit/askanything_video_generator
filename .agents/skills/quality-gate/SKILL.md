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
