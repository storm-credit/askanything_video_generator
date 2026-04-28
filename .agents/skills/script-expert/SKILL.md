---
name: script-expert
description: 스크립트 전문가 — 훅/구조/감정태그/글자수/루프 검증, 100만 쇼츠 기준
user_invocable: true
---

# /script — 스크립트 전문가

YouTube Shorts 스크립트 생성 규칙을 100만+ 조회 기준으로 관리합니다.

## 사용법

```
/script status    → 현재 스크립트 규칙 확인
/script optimize  → 전문가 기준 최적화 제안
/script check     → 최근 생성 스크립트 품질 점검
```

## 적용된 규칙 (전문가 검증 완료 2026-04-06)

### 구조 3분기
- 패턴 A: 하이네스형 (팩트/과학/우주) ← 기본
- 패턴 B: 역방향 공개형 (발견/미스터리)
- 패턴 C: 갈등-해결형 (동물/자연/생존)

### 컷1 훅
- KO: 12자 이내, 단정문, 숫자 포함 권장, 현재형 동사
- EN: 8 words 이내
- ES: 10 palabras 이내
- 질문형/명령형/감탄문 금지

### 글자수
- KO: 25~40자 필수 (25자 미만 FAIL)
- EN: 12~18 words 필수 (10w 미만 FAIL)
- ES: 10~18 palabras
- 검증 수정 시 30%+ 감소 거부

### 감정 태그 7개
- SHOCK, WONDER, TENSION, REVEAL, URGENCY, DISBELIEF, IDENTITY
- 2컷 연속 같은 태그 금지, 최소 3종류

### 리텐션 락
- 컷3~4에 반드시 배치
- 패턴 브레이크: "근데 이게 다가 아니야"

### 소프트 CTA
- 컷7~8 옵션: "이거 아는 사람?" "2편에서 더"

### 루프 엔딩
- KO/EN/US: 3패턴(질문회귀/궁금증점화/문장연결)
- LATAM: 직접 반복형

## 파일 위치
- cutter.py `_SYSTEM_PROMPT_*` (4개 언어)
- 하이네스 검증: `_verify_highness_structure()`
- 팩트 검증: `_verify_facts()`
- 글자수 가드: 검증 루프 내 30% 감소 거부
