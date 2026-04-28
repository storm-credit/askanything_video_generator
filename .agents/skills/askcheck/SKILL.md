---
name: askcheck
description: 진행사항 확인 + 전문가 5명 분석 + 오케스트라 총괄 보고. "/askcheck" 입력 시 실행.
command: askcheck
---

# /askcheck — 프로젝트 진행사항 + 전문가 분석 + 총괄 보고

## 실행 순서

### Phase 1 — 진행사항 정리
```
1. git log --oneline -20 으로 최근 커밋 확인
2. MEMORY.md 의 "Next Session TODO" 확인
3. 현재 세션에서 완료한 작업 정리
4. 남은 작업 목록 출력
```

### Phase 2 — 전문가 7명 동시 투입 (Agent 병렬)
각 전문가에게 프로젝트 전체 분석 요청. 모델 분배:

| 전문가 | 모델 | 분석 범위 |
|--------|------|----------|
| 스크립트+이미지 | Sonnet | cutter.py, formats/, imagen.py, image agent |
| TTS+자막+렌더링 | Sonnet | elevenlabs.py, whisper.py, Captions.tsx, Main.tsx, remotion.py |
| 배포+파이프라인 | Sonnet | auto_deploy.py, time_planner.py, topic_generator.py, obsidian_parser.py, youtube.py |
| 비용+설정 | Sonnet | channel_config.py, cost_tracker.py, gemini_client.py, base.py |
| 프론트엔드+UX | Sonnet | frontend/src/, API routes, SSE |
| 업로드 메타데이터 | Sonnet | upload.py, playlists.py, auto_deploy.py, topic_generator.py, series/playlist 메타 |
| 음성+말투 자연화 | Sonnet | elevenlabs.py, qwen3 tts 연동부, script polish, 채널별 tone/forbidden phrase |

### Phase 3 — 총괄 보고
전문가 7명 결과를 종합하여 아래 형식으로 보고:

```
╔══════════════════════════════════════════════╗
║  🎼 오케스트라 전문가 분석 총괄 보고          ║
╠══════════════════════════════════════════════╣
║                                              ║
║  📋 진행사항: X개 완료 / Y개 남음             ║
║                                              ║
║  🔴 즉시 수정 필요: N건                       ║
║  • 항목 리스트 (파일:라인)                    ║
║                                              ║
║  🟡 개선 권장: N건                            ║
║  • 항목 리스트                                ║
║                                              ║
║  🟢 나이스투해브: N건                         ║
║  • 항목 리스트                                ║
║                                              ║
║  💡 추가 제안: N건                            ║
║  • 새로운 기능/개선 아이디어                   ║
║                                              ║
╚══════════════════════════════════════════════╝
```

### Phase 4 — 수정 실행 여부 확인
보고 후 사용자에게 "수정 진행할까요?" 확인.
"진행" 또는 "응" 응답 시 🔴→🟡→🟢 순서로 자동 수정.

## 전문가별 체크리스트

### 스크립트+이미지 전문가
- 8포맷 프롬프트 주입 정상?
- FORMAT_CUT_GUIDE vs channel_config 일치?
- HARD FAIL 조건 완전?
- 비주얼 전략 8종 존재?
- A/B 컷1 변형 8종?
- 이미지 safety fallback 정상?
- Vision 검증 이중 호출 없음?

### TTS+자막+렌더링 전문가
- EMOTION_VOICE_DESC에 slow/pause 단어 없음?
- EMOTION_SPEED_FACTOR 전부 1.0 이상?
- 자막 문장 동시 표시 (단어별 페이드인 없음)?
- CJK 폰트 크기 계산 정확?
- CSS transition 없음 (Remotion 미지원)?
- channel prop이 remotion까지 전달?
- Whisper LCS 정렬 정상?

### 배포+파이프라인 전문가
- TTS 사전 헬스체크 존재?
- 주제별 그룹핑 동작?
- TTS 연속 실패 조기 중단?
- 크래시 복구 상태파일 보존?
- notify_success 채널명 구분?
- series_title 재생목록 연결?
- 해시태그 5개 + #쇼츠 금지?
- 설명에 해시태그 없음?
- 예약 시간 채널별 최적?

### 비용+설정 전문가
- SA 키 로테이션 연결?
- tts_speed 기본값 1.05?
- video_engine 기본값?
- Imagen 이중 검증 제거?
- 비용 추적 정확?
- 환율 하드코딩?

### 프론트엔드+UX 전문가
- 8포맷 선택 UI?
- SSE 실시간 진행?
- 채널 선택 UI?
- 에러 표시?
- 모바일 반응형?

### 업로드 메타데이터 전문가
- 업로드 직전 최종 계층에서 설명 본문 # 제거?
- 태그 5개 초과 차단?
- shorts/short/쇼츠 태그 최종 차단?
- series_title 있으면 시리즈 재생목록 연결?
- 공개 제목/설명/태그/재생목록 미리보기 가능?
- topic_generator 저장 단계에서도 메타 하드 검증?

### 음성+말투 자연화 전문가
- 한국어 말투가 딱딱하지 않은가?
- 같은 말/비슷한 말 연속 반복 차단?
- 숫자/영문/기호 발음 깨짐(r5 등) 방지?
- 감정 때문에 말이 느려지지 않는가?
- 채널별 기본 톤(anchor voice_desc) 일관적인가?
- polish 이후 훅/루프가 약해지지 않는가?
