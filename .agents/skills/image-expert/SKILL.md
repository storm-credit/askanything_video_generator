---
name: image-expert
description: 이미지 전문가 — Imagen 프롬프트 최적화, 컷1 스크롤멈추기, A/B 테스트, 채널별 비주얼
user_invocable: true
---

# /image — 이미지 전문가

YouTube Shorts 이미지 생성 파이프라인을 전문가 관점에서 관리합니다.

## 사용법

```
/image status     → 현재 이미지 설정 확인
/image optimize   → 전문가 기준 최적화 제안
/image check      → 최근 생성 이미지 품질 점검
```

## 현재 파이프라인 (전문가 검증 완료 2026-04-06)

```
cutter.py 스크립트 → 비주얼 디렉터 (Flash) → image_prompt 최적화
→ Imagen 4 생성 → A/B 컷1 3장 (기본/클로즈업/와이드) → Vision 주제 일치 검증
```

## 적용된 규칙

### 컷1 스크롤 멈추기 (4개 언어 공통)
- 극단적 스케일 대비, 강렬한 색 대비, 비현실 장면, 시선 집중 구도 중 2개 이상
- 첫 구절에 가장 충격적 시각 요소
- 65단어까지 허용 (나머지 컷 40~60)

### 비주얼 디렉터
- 피사체 이탈 방지: "script에 없는 피사체 추가 = FAIL"
- 리라이트 후 주제 일치 재검증
- 색조 일관성 앵커 (주제별 dominant hue)

### 채널별 광원
- KO: rim lighting, shadow 70:30
- EN: overcast daylight, lens flare, mid-range
- LATAM: golden hour, teal-orange, saturation +20%
- US: single practical light, 80% shadow

### Negative Prompt
- NO text/watermark/logo/diagrams/infographic/cartoon/anime/illustration

### A/B 구조화
- A(기본): 원본 프롬프트
- B(클로즈업): extreme close-up, macro, filling frame
- C(와이드): ultra wide, human silhouette for scale

## 파일 위치
- 비주얼 디렉터: `modules/gpt/cutter.py` → `_enhance_image_prompts()`
- Imagen: `modules/image/imagen.py`
- 채널 스타일: `modules/utils/channel_config.py` → `visual_style`
- Negative: `modules/utils/constants.py` → `MASTER_STYLE`
