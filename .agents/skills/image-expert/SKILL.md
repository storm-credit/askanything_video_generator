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

## Expertise Harness

### 1. Role Contract
이미지 전문가는 LLM이 만든 visual prompt를 실제 이미지 생성 엔진에 안정적으로 전달하고, 컷1 후보 중 가장 스크롤을 멈추는 이미지를 고르는 제작 전문가다.

### 2. Inputs
- `cuts[].prompt`, `cuts[].script`, `format_type`, `channel`
- `image_engine`, `image_model`, Google/Vertex SA key state
- 생성 결과 파일 경로와 Vision validator 결과

### 3. Expert Judgment Criteria
- 컷1은 클릭 유도보다 먼저 이미지 자체가 즉시 이해되어야 한다.
- 컷1 A/B는 포맷별로 다른 shot grammar를 가져야 한다.
- 나머지 컷은 주제 일치, 선명도, 9:16 composition, 무텍스트를 우선한다.
- 캐시/폴백/재시도는 비용보다 최종 생성 안정성을 우선하되 중복 Vision 호출은 줄인다.

### 4. Hard Fail
- 이미지 파일 없음, 5KB 미만, 깨진 파일.
- 텍스트/로고/워터마크/숫자 오버레이가 들어감.
- script의 중심 피사체와 이미지 피사체가 다름.
- 사람 얼굴 클로즈업 등 채널 정책상 위험한 결과.

### 5. Auto-Fix Policy
- Imagen 실패 시 Nano Banana fallback.
- safety block이면 `modules/utils/safety.py`의 안전 프롬프트로 재시도.
- 컷1은 원본 + 포맷별 변형 후보를 비교하고 최고 점수만 대표 이미지로 확정한다.

### 6. Output Contract
- `ctx.visual_paths`: 컷 수와 같은 길이.
- `ctx.cut1_ab_variants`: 컷1 후보 경로 목록.
- 실패 컷은 `None`으로 남기고 Orchestrator가 제거/중단 판단.

### 7. Code Wiring
- Runtime: `modules/orchestrator/agents/image.py`
- Engines: `modules/image/imagen.py`, `modules/image/dalle.py`
- Validator: `modules/orchestrator/agents/image_validator.py`

### 8. Verification Harness
- Good: 컷1 3개 후보 생성, Vision score 최고 후보 선택.
- Bad: 캐시 hit인데 비용 기록이 새 API 호출처럼 증가.
- Regression target: v1/v2/prepare가 같은 Cut1 A/B variant builder를 사용.
