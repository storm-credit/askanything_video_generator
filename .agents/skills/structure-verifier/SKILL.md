---
name: structure-verifier
description: 구조 검증 — 컷1 훅 + 마지막 컷 루프 점검, 채널별 훅 프로필
user_invocable: true
---

# /structure-verifier — 구조 검증

컷1(훅)과 마지막 컷(루프)만 경량 점검합니다.

## 담당 파일
- `modules/gpt/cutter/verifier.py` → `_verify_highness_structure()`, `_get_channel_hook_profile()`

## 핵심 규칙
- 범위: 컷1 + 마지막 컷만 (중간 컷 수정 안 함)
- 질문형 훅 허용 (강한 질문 OK, 약한 질문만 차단)
- 채널별 훅 프로필: askanything=도발형, wonderdrop=다큐, exploratodo=에너지, prismtale=미스터리
- 인접 컷 2개 맥락 전달 (훅-본문 단절 방지)
- 글자수 보호: max(10, 0.6x) 미만 수정 거부

## 사용법
```
/structure-verifier check → 현재 검증 규칙 확인
```
