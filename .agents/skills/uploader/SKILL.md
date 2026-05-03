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
- 공개 해시태그는 설명 본문 하단에 3~5개, 최대 5개
- #쇼츠/#Shorts/#shorts 금지
- format_type, series_title, channel 파라미터 전달
- 재생목록 자동 분류 (카테고리 7개 + 포맷 28개)

## 사용법
```
/uploader status → 인증 상태 + 최근 업로드 확인
```

## Expertise Harness

### 1. Role Contract
업로더는 공개 메타데이터와 예약 업로드를 최종 검수하는 배포 전문가다. 제목, 설명, 태그, 재생목록, 예약 시간은 업로드 직전 최종 계층에서 한 번 더 안전하게 정규화한다.

### 2. Inputs
- `video_path`, `title`, `description`, `tags`
- `channel`, `format_type`, `series_title`, `series_id`
- `privacy`, `publish_at`, OAuth channel account
- Day 파일에서 파싱된 public metadata

### 3. Expert Judgment Criteria
- 제목은 플랫폼 표시용 최종 제목이어야 하며 내부 토픽 메모를 포함하지 않는다.
- 설명 본문 하단에는 공개 해시태그 footer가 있어야 하며 최대 5개를 넘지 않는다.
- 태그는 정확히 5개를 목표로 하며, `shorts`, `short`, `쇼츠` 계열은 제거한다.
- series_title이 있으면 시리즈 재생목록 연결 결과가 state/report에 남아야 한다.

### 4. Hard Fail
- 업로드 파일 없음.
- 태그가 5개 초과 또는 forbidden tag 포함.
- 설명 공개 해시태그가 5개 초과 또는 `#Shorts/#shorts/#쇼츠` 포함.
- 예약 업로드인데 `publish_at` timezone이 불명확함.
- Day 파일 metadata를 파싱했는데 schedule/upload에서 버림.

### 5. Auto-Fix Policy
- 태그는 `#` 제거, 공백 trim, forbidden 제거, 중복 제거 후 5개로 정규화.
- 설명 안의 기존 hashtag token은 제거한 뒤, 정규화된 공개 해시태그 footer를 다시 붙인다.
- series_title은 trim/length cap 후 빈 값이면 playlist 생성 안 함.
- metadata sanitizer 결과는 audit log에 남긴다.

### 6. Output Contract
- `success`, `url`, `title`, `description`, `tags`, `playlist_results`, `metadata_audit`
- 실패 시 `error`와 실패 계층(auth/file/metadata/api)을 분리.

### 7. Code Wiring
- Upload: `modules/upload/youtube/upload.py`
- Playlists: `modules/upload/youtube/playlists.py`
- Auto deploy: `modules/scheduler/auto_deploy.py`
- Parser/scheduler: `modules/utils/obsidian_parser.py`, `modules/scheduler/time_planner.py`

### 8. Verification Harness
- Good: Day 파일의 Description/Hashtags가 최종 YouTube request까지 유지.
- Bad: sanitize 후 forbidden tag 제거 사실을 UI/로그에서 알 수 없음.
- Regression target: metadata preview와 upload request가 같은 sanitizer를 사용.
