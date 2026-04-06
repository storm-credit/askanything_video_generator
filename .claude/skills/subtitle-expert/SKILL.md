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
