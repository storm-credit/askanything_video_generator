---
name: topic-planner
description: 토픽 기획자 — GPT-5.4 주간 Day 파일 생성, 바이럴 강도 규칙
user_invocable: true
---

# /topic-planner — 토픽 기획자

주간 7일분 토픽을 GPT-5.4로 생성합니다.

## 담당 파일
- `modules/scheduler/topic_generator.py` → `generate_weekly_topics()`, `TOPIC_EXPERT_PROMPT`

## 핵심 규칙
- 모델: GPT-5.4 (OPENAI_API_KEY 자동 감지, 없으면 Gemini 폴백)
- 하루 3개 중 1개 폭발 토픽 강제
- 카테고리 최소 할당 (우주4/심해3/공룡3/지구2/동물2/기타4)
- 성과 상위 카테고리 추가 배정 허용
- 제목: 클릭 욕구 > 정보 정확성
- 포맷: 안전형보다 강한 전달 포맷 우선
- 크론: 매주 월요일 오전 9시 자동 실행

## 사용법
```
/topic-planner generate      → 즉시 7일분 생성
/topic-planner check [DayN]  → Day 파일 품질 점검
```

## Expertise Harness

### 1. Role Contract
토픽 기획자는 주간 21개 토픽을 성과 데이터, 포맷 슬롯, 중복 위험, 채널별 승리 패턴에 맞춰 편성하는 전략가다.

### 2. Inputs
- 최근 성과 데이터, 훅 패턴, 카테고리 평균
- 기존 Day 파일, topic memory, upload history
- external discovery/benchmark signals
- 8포맷 운영표와 채널별 blocked/preferred formats

### 3. Expert Judgment Criteria
- 포맷 슬롯을 먼저 정하고 토픽을 끼운다.
- 매일 1개는 폭발 후보여야 한다.
- 정확하지만 클릭 장면이 약하면 반려한다.
- Topic 1-2는 공통성, Topic 3은 채널분화 가능성을 우선한다.

### 4. Hard Fail
- 하루 3개 미만/초과.
- 하루 안에 같은 포맷 2개 이상.
- 기존 주제와 같은 팩트 축.
- Day 헤더/번호가 요청 범위와 다름.
- Description/Hashtags/Title metadata가 누락되거나 업로드 규칙 위반.

### 5. Auto-Fix Policy
- 약한 토픽은 표현 보정이 아니라 더 강한 대체안으로 교체한다.
- COUNTDOWN이 비활성 채널에서는 단일 reveal/payoff 제목으로 변환한다.
- 중복 의심은 reserve idea로 대체한다.

### 6. Output Contract
- 정확히 요청된 Day 수와 Day당 3개 토픽.
- 각 topic은 category, format, source topic, title/description/hashtags를 포함.
- 중간 분석 로그는 `data/topic_generation_logs`에 stage별 저장.

### 7. Code Wiring
- Core: `modules/scheduler/topic_generator.py`
- Parser: `modules/utils/obsidian_parser.py`
- Scheduler: `modules/scheduler/time_planner.py`

### 8. Verification Harness
- Good: Format Slate → Day Plan → Critic → Final Editor 단계가 모두 로그로 남음.
- Bad: 성과 좋은 카테고리만 채우고 클릭 장면 없는 교과서형 제목.
- Regression target: 생성 Day 파일에서 21개 토픽, 포맷 다양성, metadata hard validation 통과.
