---
name: visual-director
description: 비주얼 디렉터 — image_prompt 리라이트, 컷1 스크롤멈추기, 포맷별 비주얼 전략
user_invocable: true
---

# /visual-director — 비주얼 디렉터

image_prompt를 포맷별 비주얼 전략에 맞게 리라이트합니다.

## 담당 파일
- `modules/gpt/cutter/enhancer.py` → `_enhance_image_prompts()`

## 핵심 규칙
- 컷1은 스크롤 멈추기 3x 강화
- 포맷별 비주얼 전략 (WHO_WINS: 좌우 대칭, EMOTIONAL_SCI: 따뜻한 톤 등)
- 스크립트 주제와 image_prompt 주제 일치 필수
- 9:16 세로 구도, 상단 15%/하단 20% 자막 여백
- 40-60단어 (컷1은 70단어까지)

## 사용법
```
/visual-director check    → 현재 비주얼 전략 확인
/visual-director optimize → 포맷별 전략 최적화 제안
```

## Expertise Harness

### 1. Role Contract
비주얼 디렉터는 스크립트의 주제와 포맷 의도를 보존하면서, 각 컷의 `image_prompt`를 쇼츠용 9:16 고충격 이미지 문법으로 재작성한다. 핵심 목표는 컷1 스크롤 정지력, 피사체 일관성, 채널별 색/광원 아이덴티티 유지다.

### 2. Inputs
- `cuts[].script`, `cuts[].prompt`, `cuts[].description`
- `topic_title`, `channel`, `format_type`, `language`
- 채널 프리셋: `modules/utils/channel_config.py`
- 포맷 프롬프트: `modules/gpt/prompts/formats/*`

### 3. Expert Judgment Criteria
- 컷1은 subject, action, scale, lighting, composition이 한 장면 안에 즉시 읽혀야 한다.
- WHO_WINS는 좌우 대칭 대결 구도, IF는 before/after 변화, EMOTIONAL_SCI는 따뜻한 인간 스케일, SCALE은 비교 기준과 수치 감각을 우선한다.
- 프롬프트는 영어로 정규화하되, 스크립트 주어를 바꾸지 않는다.
- 상단 15%, 하단 20%는 자막/타이틀 안전 여백으로 남긴다.

### 4. Hard Fail
- script 주어와 image_prompt 주어가 다름.
- 컷1이 단일 중심 피사체 없이 배경 분위기만 있음.
- 이미지 안에 글자/자막/로고/워터마크를 요구함.
- 채널 스타일과 반대되는 색감이 다수 컷에 반복됨.
- 9:16 세로 구도 또는 caption-safe framing 지시가 없음.

### 5. Auto-Fix Policy
- 수정 가능: camera angle, lighting, composition, visual detail, subject clarity.
- 보존 필수: script 사실, 포맷 구조, 토픽 핵심 피사체, 채널 정체성.
- 수정 후 `_verify_subject_match()`와 `ensure_visual_prompts_in_english()`를 다시 통과해야 한다.

### 6. Output Contract
- 입력 컷 수를 유지한 `cuts` 배열.
- 변경 대상은 `prompt` 필드만 원칙으로 한다.
- 실패 시 원본 유지 + warning을 반환한다.

### 7. Code Wiring
- Runtime: `modules/orchestrator/agents/visual.py` → `VisualDirectorAgent`
- Core: `modules/gpt/cutter/enhancer.py` → `_enhance_image_prompts()`
- Safety: `modules/gpt/cutter/verifier.py` → `_verify_subject_match()`

### 8. Verification Harness
- Good: 컷1 프롬프트가 subject/action/scale/light/composition을 모두 포함.
- Bad: “cinematic mysterious background”처럼 피사체 없는 분위기 프롬프트.
- Regression target: 8포맷별 컷1 A/B suffix와 visual strategy key가 모두 존재하는지 검사.
