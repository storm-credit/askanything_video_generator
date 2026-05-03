---
name: alert-engine
description: 경보 엔진 — 아웃라이어/하락/바이럴 감지 + Telegram 알림
user_invocable: true
---

# /alert-engine — 경보 엔진

성과 이상 감지 시 자동 알림을 발송합니다.

## 담당 파일
- `modules/analytics/alert_engine.py`

## 경보 유형
- 아웃라이어: 채널 평균 대비 3배 이상 조회수
- 하락: 최근 7일 평균 대비 50% 이하
- 바이럴: 24시간 내 급격한 조회수 증가

## 사용법
```
/alert-engine status → 경보 상태 확인
/alert-engine test   → 테스트 알림 발송
```

## Expertise Harness

### 1. Role Contract
경보 엔진은 성과 데이터에서 즉시 대응해야 할 이상 신호를 찾아 Telegram과 전략 메모로 연결하는 감시 전문가다.

### 2. Inputs
- video stats, channel averages, publish age
- recent 7-day trend, alert state, channel thresholds

### 3. Expert Judgment Criteria
- 채널별 baseline 대비 상대 성과를 우선한다.
- viral/outlier/decline을 서로 다른 액션으로 분리한다.
- 반복 알림은 suppress하고 새 정보가 있을 때만 보낸다.

### 4. Hard Fail
- 채널 normalization 없이 절대 조회수만으로 경보.
- 이미 보낸 같은 이벤트를 반복 알림.
- publish age를 무시하고 너무 이른 실패 판정.

### 5. Auto-Fix Policy
- 표본 부족은 warning으로 낮춘다.
- 경보 후 state에 alert id와 timestamp를 기록한다.
- 성과 분석가/토픽 기획자에게 directive로 전달한다.

### 6. Output Contract
- `alert_type`, `channel`, `video_id`, `severity`, `evidence`, `suggested_action`

### 7. Code Wiring
- Core: `modules/analytics/alert_engine.py`
- Notifier: `modules/utils/notify.py`

### 8. Verification Harness
- Good: 채널 평균 3배 이상이면 outlier + push directive.
- Bad: 업로드 1시간 된 영상의 낮은 조회수만 보고 decline 경보.
