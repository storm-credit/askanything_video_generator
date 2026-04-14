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
