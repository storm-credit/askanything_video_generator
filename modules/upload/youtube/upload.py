import os
import re
import time
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from .auth import _get_credentials
from .playlists import add_to_playlist, add_to_format_playlist, add_to_series_playlist
from .engagement import _build_related_comment, _post_pinned_comment


def _sanitize_youtube_tags(tags: list[str] | None) -> list[str]:
    forbidden = {"shorts", "short", "쇼츠"}
    cleaned: list[str] = []
    seen: set[str] = set()
    for tag in tags or []:
        value = str(tag).replace("#", "").strip()
        if not value:
            continue
        lowered = value.lower()
        if lowered in forbidden or lowered in seen:
            continue
        seen.add(lowered)
        cleaned.append(value)
        if len(cleaned) >= 5:
            break
    return cleaned


def _sanitize_youtube_description(description: str | None) -> str:
    """YouTube 본문 설명에서 공개 해시태그 토큰을 최종 제거."""
    text = str(description or "")
    text = re.sub(r"(?<!\w)#[\w가-힣ぁ-んァ-ヶ一-龥ÁÉÍÓÚÜÑáéíóúüñ-]+", "", text)
    text = text.replace("#", "")
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(line.rstrip() for line in text.splitlines()).strip()


def _prepare_youtube_metadata(description: str | None, tags: list[str] | None) -> tuple[str, list[str]]:
    """업로드 직전 공개 메타데이터 최종 안전장치.

    프론트/자동배포/수동 API 어느 경로로 들어와도 같은 규칙을 적용한다.
    """
    cleaned_description = _sanitize_youtube_description(description)
    cleaned_tags = _sanitize_youtube_tags(tags)
    forbidden = {"shorts", "short", "쇼츠"}

    if "#" in cleaned_description:
        raise ValueError("YouTube 설명 본문에는 #해시태그를 넣을 수 없습니다.")
    if len(cleaned_tags) > 5:
        raise ValueError("YouTube 태그는 최대 5개까지만 허용됩니다.")
    bad_tags = [tag for tag in cleaned_tags if tag.lower() in forbidden]
    if bad_tags:
        raise ValueError(f"YouTube 태그에 금지어가 포함되어 있습니다: {', '.join(bad_tags)}")
    if any("#" in tag for tag in cleaned_tags):
        raise ValueError("YouTube 태그에는 # 문자를 포함할 수 없습니다.")

    return cleaned_description, cleaned_tags


def upload_video(
    video_path: str,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    privacy: str = "private",
    category_id: str = "22",
    channel_id: str = None,
    publish_at: str | None = None,
    format_type: str | None = None,
    series_id: str | None = None,
    series_title: str | None = None,
    channel: str = "",
    task_date: str | None = None,
    topic_group: str | None = None,
) -> dict:
    """YouTube에 동영상을 업로드합니다.

    publish_at: 예약 공개 시간 (ISO 8601, e.g. "2026-03-20T15:00:00Z").
               설정 시 privacyStatus가 자동으로 "private"으로 변경됩니다.
    """
    from datetime import datetime, timezone

    creds = _get_credentials(channel_id)
    if not creds:
        raise PermissionError("YouTube 인증이 필요합니다. 먼저 계정을 연동해주세요.")

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"동영상 파일을 찾을 수 없습니다: {video_path}")

    description, tags = _prepare_youtube_metadata(description, tags)

    # 예약 공개 검증
    if publish_at:
        try:
            scheduled_dt = datetime.fromisoformat(publish_at.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"예약 시간 형식이 올바르지 않습니다: {publish_at} (ISO 8601 필요)")
        if scheduled_dt <= datetime.now(timezone.utc):
            raise ValueError("예약 시간은 현재 시간 이후여야 합니다.")

    youtube = build("youtube", "v3", credentials=creds)

    status_body: dict = {
        "privacyStatus": "private" if publish_at else privacy,
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": True,  # AI 생성/변경 콘텐츠 자동 선언
    }
    if publish_at:
        status_body["publishAt"] = publish_at

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": status_body,
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        resumable=True,
        chunksize=5 * 1024 * 1024,  # 5MB chunks (256KB → 5MB, 업로드 속도 개선)
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    print(f"-> [YouTube] 업로드 시작: {title}")
    response = None
    retry_count = 0
    max_retries = 3
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                print(f"   업로드 진행: {pct}%")
            retry_count = 0
        except HttpError as e:
            status_code = int(getattr(getattr(e, "resp", None), "status", 0) or 0)
            if status_code in {500, 502, 503, 504} and retry_count < max_retries:
                retry_count += 1
                wait = min(30, 2 ** retry_count)
                print(f"   [YouTube] 업로드 재시도 {retry_count}/{max_retries} ({status_code}) — {wait}초 대기")
                time.sleep(wait)
                continue
            raise
        except (OSError, ConnectionError, TimeoutError) as e:
            if retry_count < max_retries:
                retry_count += 1
                wait = min(30, 2 ** retry_count)
                print(f"   [YouTube] 업로드 연결 재시도 {retry_count}/{max_retries}: {e} — {wait}초 대기")
                time.sleep(wait)
                continue
            raise

    video_id = response["id"]
    video_url = f"https://youtube.com/shorts/{video_id}"
    print(f"OK [YouTube] 업로드 완료! {video_url}")

    result = {
        "success": True,
        "video_id": video_id,
        "url": video_url,
        "title": title,
        "privacy": "private" if publish_at else privacy,
    }
    if publish_at:
        result["scheduled_at"] = publish_at
        print(f"   [YouTube] 예약 공개: {publish_at}")

    if task_date and topic_group:
        try:
            from modules.utils.today_tasks import upsert_task_status

            upsert_task_status(
                task_date=task_date,
                topic_group=topic_group,
                channel=channel or "",
                title=title,
                status="completed",
                source="youtube_upload",
                video_path=video_path,
                youtube_url=video_url,
            )
        except Exception as e:
            print(f"   [오늘할일 DB] 업로드 직후 완료 기록 실패 (업로드는 성공): {e}")

    try:
        from modules.utils.upload_history import upsert_videos

        upsert_videos(
            channel or "",
            [{
                "video_id": video_id,
                "title": title,
                "published_at": publish_at or datetime.now(timezone.utc).isoformat(),
            }],
            source="upload_success",
        )
    except Exception as e:
        print(f"   [업로드 히스토리] DB 저장 실패 (업로드는 성공): {e}")

    # 재생목록 자동 추가
    try:
        playlist_id = add_to_playlist(video_id, title, tags or [], channel_id, channel=channel)
        if playlist_id:
            result["playlist_id"] = playlist_id
    except Exception as e:
        print(f"   [재생목록] 자동 추가 실패 (업로드는 성공): {e}")

    # 포맷별 재생목록 추가
    if format_type:
        try:
            add_to_format_playlist(video_id, format_type, channel_id, channel)
        except Exception as e:
            print(f"   [포맷 재생목록] 추가 실패 (업로드는 성공): {e}")

    # 시리즈별 재생목록 추가
    if series_title:
        try:
            series_playlist_id = add_to_series_playlist(video_id, series_id, series_title, channel_id, channel)
            if series_playlist_id:
                result["series_playlist_id"] = series_playlist_id
        except Exception as e:
            print(f"   [시리즈 재생목록] 추가 실패 (업로드는 성공): {e}")

    # 고정 댓글 — 같은 카테고리 과거 영상 링크
    try:
        comment_text = _build_related_comment(video_id, title, tags or [], channel_id, channel)
        if comment_text:
            _post_pinned_comment(video_id, comment_text, channel_id)
            result["pinned_comment"] = True
    except Exception as e:
        print(f"   [고정 댓글] 실패 (업로드는 성공): {e}")

    return result
