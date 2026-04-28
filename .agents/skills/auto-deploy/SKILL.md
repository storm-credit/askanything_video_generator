---
name: auto-deploy
description: 오늘 Day 파일 → 채널별 영상 자동 생성 + 예약 업로드
user_invocable: true
---

# /deploy — 자동 배포

오늘 Day 파일의 주제를 자동으로 영상 생성 + YouTube 예약 업로드합니다.

## 사용법

```
/deploy              → 오늘 Day 파일 배포 (채널당 최대 3개)
/deploy preview      → 스케줄 미리보기 (생성 없이)
/deploy 2026-04-06   → 특정 날짜 배포
/deploy status       → 진행 상태 확인
```

## 실행 방법

1. **미리보기**: `curl -s "http://localhost:8003/api/scheduler/preview"` 로 스케줄 확인
2. **실행**: `curl -s -X POST "http://localhost:8003/api/scheduler/run?max_per_channel=3"` 로 배포 시작
3. **상태 확인**: `curl -s "http://localhost:8003/api/scheduler/status"` 로 진행 상태 확인

## 파이프라인

```
Day 파일 파싱 → 채널별 주제 추출 → 시간 자동 분배
→ cutter.py 스크립트 생성 (Pro) → 비주얼 디렉터 image_prompt 최적화
→ Imagen 이미지 생성 (A/B 3장) → ElevenLabs TTS
→ Remotion 렌더 → YouTube 예약 업로드 (publishAt)
```

## 채널별 업로드 시간 (KST)
- AskAnything: 18:00~21:00
- WonderDrop: 06:00~09:00
- ExploraTodo: 09:00~12:00
- PrismTale: 07:00~10:00
