---
name: performance-analyst
description: 성과 분석가 — 4채널 조회수/훅패턴/카테고리 성과 분석
user_invocable: true
---

# /performance-analyst — 성과 분석가

4채널 YouTube 성과 데이터를 수집하고 분석합니다.

## 담당 파일
- `modules/analytics/performance_tracker.py` → `record_daily()`, `analyze_hook_patterns()`
- `modules/scheduler/weekly_stats_update.py` → `collect_and_analyze()`
- `modules/analytics/alert_engine.py` → 아웃라이어/하락/바이럴 감지

## 핵심 기능
- 일일 성과 스냅샷 기록 (크론 23:50)
- 훅 패턴 7종 분류 + 패턴별 평균 조회수
- 카테고리별 평균 조회수
- 아웃라이어/하락/바이럴 경보 (Telegram)

## 사용법
```
/performance-analyst report   → 최근 성과 리포트
/performance-analyst alerts   → 경보 상태 확인
/performance-analyst hooks    → 훅 패턴별 성과
```

## Expertise Harness

### 1. Role Contract
성과 분석가는 단순 리포터가 아니라 다음 주 토픽/포맷/훅 전략으로 데이터를 번역하는 전략 전문가다.

### 2. Inputs
- YouTube video stats: views, likes, comments, publish time
- channel, category, format_type, hook pattern, topic title
- recent averages, weekly trend, outlier/decline alert state

### 3. Expert Judgment Criteria
- 조회수 절대값보다 채널 기준 대비 초과 성과를 우선한다.
- 24h 초기 속도, 7일 누적, 장기 evergreen을 분리해서 판단한다.
- 훅 패턴은 카테고리와 함께 본다. 같은 훅이라도 우주/심해/동물에서 결과가 다를 수 있다.
- 다음 액션은 `push`, `test`, `avoid`, `retire`로 분리한다.

### 4. Hard Fail
- 채널 평균 대비 normalization 없이 채널 간 조회수를 직접 비교.
- 표본 수 3개 미만 패턴을 승리 패턴으로 확정.
- 업로드 시간/채널/포맷을 무시하고 제목만 분석.
- 경보를 만들고 topic planner로 feedback하지 않음.

### 5. Auto-Fix Policy
- 표본 부족 항목은 `candidate`로 낮춘다.
- 급락/아웃라이어는 Telegram alert와 weekly strategy note에 동시에 남긴다.
- 중복 주제/실패 패턴은 topic_generator의 avoid list로 전달한다.

### 6. Output Contract
- `winning_patterns`, `declining_patterns`, `category_moves`, `topic_directives`, `alerts`
- 각 directive는 channel, evidence, confidence, action을 포함.

### 7. Code Wiring
- Stats: `modules/analytics/performance_tracker.py`
- Alerts: `modules/analytics/alert_engine.py`
- Weekly update: `modules/scheduler/weekly_stats_update.py`
- Topic feedback: `modules/scheduler/topic_generator.py`

### 8. Verification Harness
- Good: “askanything 심해+질문형 훅 push, wonderdrop WHO_WINS avoid”처럼 채널별 행동 지시가 나온다.
- Bad: “조회수 높은 주제 더 하자” 수준의 일반 리포트.
- Regression target: sample stats fixture에서 같은 directive가 재현.
