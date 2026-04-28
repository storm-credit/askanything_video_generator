---
name: uploader
description: 업로더 — YouTube 예약 업로드, 재생목록 분류, 해시태그 관리
user_invocable: true
---

# /uploader — 업로더

생성된 영상을 YouTube에 예약 업로드합니다.

## 담당 파일
- `modules/upload/youtube/upload.py` → `upload_video()`
- `modules/upload/youtube/playlists.py` → 카테고리/포맷/시리즈 재생목록
- `modules/upload/youtube/auth.py` → OAuth 인증

## 핵심 규칙
- 해시태그 5개 제한, #쇼츠 금지
- 설명에 해시태그 금지
- format_type, series_title, channel 파라미터 전달
- 재생목록 자동 분류 (카테고리 7개 + 포맷 28개)

## 사용법
```
/uploader status → 인증 상태 + 최근 업로드 확인
```
