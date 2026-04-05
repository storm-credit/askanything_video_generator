---
name: channel-stats
description: 4채널 YouTube 성과 데이터 수집 + 분석 리포트
user_invocable: true
---

# /stats — 채널 성과 분석

YouTube 4채널 성과 데이터를 수집하고 분석 리포트를 생성합니다.

## 사용법

```
/stats              → 전 채널 통계 조회 (캐시)
/stats refresh      → 새로 수집
/stats wonderdrop   → 특정 채널만
```

## 실행 방법

1. `curl -s "http://localhost:8003/api/stats/all?refresh=true"` 로 전 채널 수집
2. 결과 분석 후 요약 출력
3. 성과_분석_리포트.md 업데이트

## 분석 항목
- 채널별 총 조회/평균/Top 5
- 카테고리별 성과 (우주/공룡/동물/지구)
- 최근 7일 성장률
- 상승/하락 카테고리
