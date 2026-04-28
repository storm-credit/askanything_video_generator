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
