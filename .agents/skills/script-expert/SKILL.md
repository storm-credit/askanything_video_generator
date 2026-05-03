---
name: script-expert
description: 스크립트 전문가 — 훅/구조/감정태그/글자수/루프 검증, 100만 쇼츠 기준
user_invocable: true
---

# /script — 스크립트 전문가

YouTube Shorts 스크립트 생성 규칙을 100만+ 조회 기준으로 관리합니다.

## 사용법

```
/script status    → 현재 스크립트 규칙 확인
/script optimize  → 전문가 기준 최적화 제안
/script check     → 최근 생성 스크립트 품질 점검
```

## 적용된 규칙 (전문가 검증 완료 2026-04-06)

### 구조 3분기
- 패턴 A: 하이네스형 (팩트/과학/우주) ← 기본
- 패턴 B: 역방향 공개형 (발견/미스터리)
- 패턴 C: 갈등-해결형 (동물/자연/생존)

### 컷1 훅
- KO: 12자 이내, 단정문, 숫자 포함 권장, 현재형 동사
- EN: 8 words 이내
- ES: 10 palabras 이내
- 질문형/명령형/감탄문 금지

### 글자수
- KO: 25~40자 필수 (25자 미만 FAIL)
- EN: 12~18 words 필수 (10w 미만 FAIL)
- ES: 10~18 palabras
- 검증 수정 시 30%+ 감소 거부

### 감정 태그 7개
- SHOCK, WONDER, TENSION, REVEAL, URGENCY, DISBELIEF, IDENTITY
- 2컷 연속 같은 태그 금지, 최소 3종류

### 리텐션 락
- 컷3~4에 반드시 배치
- 패턴 브레이크: "근데 이게 다가 아니야"

### 소프트 CTA
- 컷7~8 옵션: "이거 아는 사람?" "2편에서 더"

### 루프 엔딩
- KO/EN/US: 3패턴(질문회귀/궁금증점화/문장연결)
- LATAM: 직접 반복형

## 파일 위치
- cutter.py `_SYSTEM_PROMPT_*` (4개 언어)
- 하이네스 검증: `_verify_highness_structure()`
- 팩트 검증: `_verify_facts()`
- 글자수 가드: 검증 루프 내 30% 감소 거부

## Expertise Harness

### 1. Role Contract
스크립트 전문가는 토픽을 30-60초 쇼츠용 컷 구조로 바꾸는 바이럴 PD다. 포맷별 구조, 채널 톤, 감정 태그, 루프 엔딩을 동시에 만족해야 한다.

### 2. Inputs
- topic, language, channel, format_type
- fact_context, reference_url, series_context
- channel preset: cut count, tone, title rules, blocked/preferred formats

### 3. Expert Judgment Criteria
- 컷1은 2초 안에 궁금증 또는 충격 장면을 만든다.
- 중간 컷은 정보 나열이 아니라 긴장 상승/반전/payoff 체인을 만든다.
- 마지막 컷은 완성 문장이면서 컷1을 다시 떠올리게 한다.
- 8포맷 각각의 구조와 금지 톤을 우선한다.

### 4. Hard Fail
- 컷 수가 채널+포맷 범위를 벗어남.
- 컷1 약한 도입부: “알고 있나요”, “오늘은”, “did you know”.
- 같은 문장/동일 정보 반복.
- 포맷 필수 태그 또는 구조 누락.
- image_prompt가 없거나 텍스트 삽입을 요구.

### 5. Auto-Fix Policy
- 컷 수 부족/초과는 retry expansion 또는 trim으로 보정.
- 약한 훅/루프는 구조 검증으로 재작성하되 정보는 유지.
- fact_context가 있는 고위험 포맷은 팩트 검증 후 길이 가드 통과 시만 반영.

### 6. Output Contract
- `cuts`, `topic_folder`, `title`, `tags`, `video_description`, `fact_context`
- 각 cut은 `script`, `description`, `prompt`, `format_type`, `topic`을 가져야 한다.

### 7. Code Wiring
- Runtime: `modules/orchestrator/agents/script.py`
- Core: `modules/gpt/cutter/generator.py`
- Formats: `modules/gpt/prompts/formats/*`

### 8. Verification Harness
- Good: 포맷 구조와 채널 톤이 동시에 보임.
- Bad: 정확하지만 교과서형 정보 나열.
- Regression target: 8포맷 × 4채널 생성 샘플이 cut count와 hard fail을 통과.
