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

## Expertise Harness

### 1. Role Contract
구조 검증자는 전체 대본을 갈아엎지 않고 컷1 훅과 마지막 루프만 전문적으로 점검한다.

### 2. Inputs
- Cut 1, Cut 2 context, second-last cut, last cut
- topic, channel hook profile, language, loop style

### 3. Expert Judgment Criteria
- 훅은 채널 프로필에 맞는 즉시성/구체성/긴장을 가져야 한다.
- 루프는 빈 CTA가 아니라 테마를 되돌리는 완성 문장이어야 한다.
- 질문형은 무조건 금지하지 않고 채널/포맷에 맞으면 허용한다.

### 4. Hard Fail
- 약한 도입부 또는 일반 설명형 시작.
- 마지막 컷 미완성 문장.
- “다음에 알려줄게” 같은 빈 약속 CTA.
- 수정 후 글자수가 과도하게 줄어 정보가 사라짐.

### 5. Auto-Fix Policy
- 수정 범위는 컷1과 마지막 컷의 `script`만.
- 주변 컷 맥락과 충돌하면 원본 유지.
- 글자수 보호 가드 통과 시만 적용.

### 6. Output Contract
- `hook_ok`, `loop_ok`, `fixes[]`
- fixes는 cut 번호, field, original, fixed를 포함.

### 7. Code Wiring
- Core: `modules/gpt/cutter/verifier.py` → `_verify_highness_structure()`
- Channel profile: `modules/utils/channel_config.py`

### 8. Verification Harness
- Good: 약한 훅만 바꾸고 중간 컷은 그대로 유지.
- Bad: 루프를 “2편에서 공개” 같은 빈 CTA로 바꿈.
- Regression target: 질문형 강한 훅은 통과, 약한 질문형만 수정.
