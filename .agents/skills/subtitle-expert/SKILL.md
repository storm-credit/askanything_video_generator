---
name: subtitle-expert
description: 자막 전문가 — 채널별 자막 스타일, 폰트, 크기, 위치, 애니메이션 관리
user_invocable: true
---

# /subtitle — 자막 전문가

YouTube Shorts 4채널 자막 디자인을 전문가 기준으로 관리합니다.

## 사용법

```
/subtitle status   → 현재 4채널 자막 설정 확인
/subtitle optimize → 전문가 기준 최적화 제안
```

## 현재 설정 (전문가 검증 완료 2026-04-06)

### KO (AskAnything) — 카라오케 스타일
- 폰트: Pretendard 900
- 크기: 95px
- 위치: 47% (중앙)
- 스타일: 단어별 카라오케, 현재 단어 노란색 #FFE600
- 팝업: 활성 단어 scale 1.12
- 외곽선: 3px black + 8방향 solid shadow

### EN (WonderDrop) — 단어별 하이라이트
- 폰트: Montserrat 900
- 크기: 100px
- 위치: 47%
- 스타일: 감정 색상 하이라이트 + 글로우 12px
- 팝업: 활성 1.1x, 강조 1.18x
- 외곽선: 5px black + 4px shadow + glow

### ES-LATAM (ExploraTodo) — 에너지
- 폰트: Montserrat 900 (권장: Bebas Neue로 전환 검토)
- 크기: 100px (권장: 110px)
- 외곽선: 5px (권장: 6px)
- 색상: 네온 계열 (#FF2020, #FFE600, #00FF66)

### ES-US (PrismTale) — 다크 시네마틱
- 폰트: Montserrat 900 (권장: Poppins SemiBold 검토)
- 크기: 100px (권장: 95px)
- 비활성: 회색 #BBBBBB 70%
- 위치: 47% (권장: 35~38%)

## 채널별 완전 분리 (미구현)
- 현재: CJK(한국어) vs 라틴(EN/ES) 2분기
- 목표: KO/EN/ES-LATAM/ES-US 4분기
- 필요: Remotion에 channel prop 전달 → Main.tsx 수정

## 파일 위치
- Remotion: `remotion/src/Captions.tsx`
- 채널 설정: `modules/utils/channel_config.py` → `caption_size`, `caption_y`

## Expertise Harness

### 1. Role Contract
자막 전문가는 채널별 읽기 리듬과 화면 안전성을 관리한다. 목표는 모바일 9:16 화면에서 자막이 얼굴/피사체/버튼 영역을 가리지 않고, 한눈에 읽히게 하는 것이다.

### 2. Inputs
- `scripts`, `word_timestamps`, `descriptions`, `channel`
- `caption_size`, `caption_y`, `language`
- Remotion composition props from `modules/video/remotion.py`

### 3. Expert Judgment Criteria
- KO: 굵고 짧은 문장, 과한 단어별 깜빡임보다 안정적인 phrase display.
- EN: documentary tone에 맞게 과한 네온보다 명확한 emphasis.
- ES-LATAM: 에너지와 색 대비 허용, 단 모바일 overflow 금지.
- ES-US: 다크 시네마틱 톤, 낮은 채도/차분한 하이라이트.

### 4. Hard Fail
- 자막 텍스트가 부모 너비를 넘거나 화면 밖으로 나감.
- CSS transition 등 Remotion frame deterministic 렌더에 부적합한 스타일.
- 긴 CJK 단어가 shrink/overflowWrap 없이 잘림.
- `channel` prop이 Remotion까지 전달되지 않아 채널 스타일이 적용 안 됨.

### 5. Auto-Fix Policy
- longest-token 기준으로 font size를 축소한다.
- mobile safe width를 우선하고, 필요 시 phrase length를 줄인다.
- timestamp가 없으면 script 기반 fallback timing을 사용한다.

### 6. Output Contract
- Remotion props에 `channel`, `captionSize`, `captionY`, `wordTimestamps` 포함.
- Captions 컴포넌트는 frame 기반 deterministic style만 사용.

### 7. Code Wiring
- Renderer: `remotion/src/Captions.tsx`, `remotion/src/Main.tsx`
- Backend props: `modules/video/remotion.py`
- Timestamp source: `modules/transcription/whisper.py`

### 8. Verification Harness
- Good: 390px 모바일 폭에서도 가장 긴 단어가 자막 박스 안에 들어감.
- Bad: 이전 결과의 caption 설정이 새 채널 렌더에 섞임.
- Regression target: desktop/mobile screenshot에서 자막 overflow와 overlap 검사.
