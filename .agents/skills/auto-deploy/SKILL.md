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

## Expertise Harness

### 1. Role Contract
자동 배포 에이전트는 Day 파일을 실제 예약 업로드까지 끊기지 않게 이어주는 운영 총괄이다. 목표는 상태 보존, 중복 방지, 채널별 예약 품질, 실패 시 안전 중단이다.

### 2. Inputs
- Day 파일, parsed topics, public metadata
- channel schedule windows, publish mode, max_per_channel
- deploy state, upload history, key/TTS health

### 3. Expert Judgment Criteria
- 이미 성공한 결과는 precheck 실패나 재시도 중에도 보존한다.
- 채널별 topic grouping과 예약 시간이 의도대로 유지되어야 한다.
- TTS/API 연속 실패는 조기 중단하고 다음 run에서 복구 가능해야 한다.

### 4. Hard Fail
- 기존 성공 state를 덮어씀.
- TTS health check가 실제 fallback 정책과 불일치.
- 같은 주제/채널이 중복 업로드됨.
- 예약 URL에 부가 문구가 붙어 버튼 URL이 깨짐.

### 5. Auto-Fix Policy
- precheck 실패 시 기존 state merge 후 실패 상태만 기록.
- TTS_ENGINE별 health check로 분기.
- 실패 항목은 state에 남기고 성공 항목은 재처리하지 않는다.

### 6. Output Contract
- `success`, `aborted`, `results`, `failures`, `state_path`
- Telegram 알림은 채널, 제목, URL, 예약 시간을 분리한다.

### 7. Code Wiring
- Core: `modules/scheduler/auto_deploy.py`
- Parser: `modules/utils/obsidian_parser.py`
- Scheduler: `modules/scheduler/time_planner.py`

### 8. Verification Harness
- Good: 12개 중 8개 성공 후 TTS precheck 실패해도 8개 성공 state 유지.
- Bad: precheck 실패가 당일 deploy state를 빈 결과로 덮음.
- Regression target: interrupted run resume fixture.
