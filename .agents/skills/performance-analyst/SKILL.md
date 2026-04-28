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
