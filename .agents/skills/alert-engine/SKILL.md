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
