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
