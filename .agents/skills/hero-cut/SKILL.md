---
name: hero-cut
description: 히어로컷 전문가 — 포맷별 감정태그 기반 Veo3 영상 컷 선택
user_invocable: true
---

# /hero-cut — 히어로컷 전문가

포맷별 감정 태그 기반으로 Veo3 영상화할 컷을 선택합니다.

## 담당 파일
- `modules/video/veo3.py`
- `modules/video/video.py` → 포맷별 히어로컷 선택 로직

## 핵심 규칙
- 감정 태그 기반 컷 선택 (SHOCK/REVEAL/CLIMAX 우선)
- hero-only 모드: 1컷만 Veo3, 나머지 정적 이미지
- 비용 최적화: 영상당 Veo3 1회만 호출

## 사용법
```
/hero-cut rules → 포맷별 히어로컷 선택 기준
```

## Expertise Harness

### 1. Role Contract
히어로컷 전문가는 비용을 제한하면서 영상 효과가 가장 큰 1개 컷을 고른다. hero-only 모드에서는 이 선택이 영상 전체의 체감 품질을 좌우한다.

### 2. Inputs
- `cuts[].description`, `cuts[].script`, `cuts[].prompt`
- `format_type`, `channel`, `video_engine`, 비용 제한
- emotion tags: SHOCK, REVEAL, CLIMAX, URGENCY, DISBELIEF, WONDER, LOOP

### 3. Expert Judgment Criteria
- 컷1은 스크롤 정지력이 강하면 우선 후보.
- REVEAL/CLIMAX는 payoff가 시각적으로 큰 경우 우선.
- WHO_WINS는 CLASH/CLIMAX/REVEAL, IF는 변화 순간, SCALE은 최대 스케일 비교 컷을 우선.
- EMOTIONAL_SCI는 충격보다 WONDER/IDENTITY의 아름다운 장면을 우선.

### 4. Hard Fail
- 비용 제한이 hero-only인데 2개 이상 Veo3 호출.
- 선택 컷에 이미지 프롬프트가 없거나 피사체가 불명확함.
- LOOP만 있고 실제 motion payoff가 없음.
- 정적 이미지 fallback 없이 비디오 실패로 전체 렌더 중단.

### 5. Auto-Fix Policy
- 후보 점수 동률이면 앞쪽 컷, 그다음 컷1을 우선한다.
- 비디오 엔진 실패 시 해당 컷도 정적 이미지로 fallback.
- 선택 이유를 로그/state에 남긴다.

### 6. Output Contract
- `hero_cut_index`, `reason`, `emotion_tag`, `format_reason`, `fallback_used`
- hero-only가 아니면 `selected_cut_indices` 배열.

### 7. Code Wiring
- Hero helper: `modules/utils/hero_cuts.py`
- Video runtime: `modules/orchestrator/agents/video.py`
- Engines: `modules/video/engines.py`, `modules/video/veo.py`, `modules/video/kling.py`

### 8. Verification Harness
- Good: WHO_WINS에서 컷8 CLIMAX 또는 컷10 REVEAL이 컷1보다 더 큰 payoff면 선택.
- Bad: 모든 포맷에서 무조건 컷1만 선택.
- Regression target: 포맷별 fixture로 hero index가 기대값과 일치.
