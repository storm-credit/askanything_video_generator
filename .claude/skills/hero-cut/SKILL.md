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
