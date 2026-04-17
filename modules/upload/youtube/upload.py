import os
import re
from googleapiclient.discovery import build
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

    tags = _sanitize_youtube_tags(tags)
    description = _sanitize_youtube_description(description)

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
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"   업로드 진행: {pct}%")

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
            add_to_series_playlist(video_id, series_id, series_title, channel_id, channel)
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
