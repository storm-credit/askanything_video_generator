from googleapiclient.discovery import build

from .auth import _get_credentials
from .playlists import _detect_category, _get_playlist_lang, ensure_playlists, CHANNEL_PLAYLISTS


def _build_related_comment(video_id: str, title: str, tags: list[str],
                           channel_id: str = None, channel: str = None) -> str | None:
    """같은 카테고리의 과거 영상 2-3개를 찾아 고정 댓글 텍스트 생성."""
    category = _detect_category(title, tags, channel=channel)
    if not category:
        return None

    creds = _get_credentials(channel_id)
    if not creds:
        return None

    youtube = build("youtube", "v3", credentials=creds)
    lang = _get_playlist_lang(channel)

    # 같은 재생목록에서 영상 가져오기
    playlists = ensure_playlists(channel_id, channel)
    playlist_id = playlists.get(category)
    if not playlist_id:
        return None

    try:
        resp = youtube.playlistItems().list(
            part="snippet", playlistId=playlist_id, maxResults=10,
        ).execute()

        related = []
        for item in resp.get("items", []):
            vid = item["snippet"]["resourceId"]["videoId"]
            if vid == video_id:
                continue  # 자기 자신 제외
            vtitle = item["snippet"]["title"]
            related.append({"title": vtitle, "url": f"https://youtube.com/shorts/{vid}"})

        if not related:
            return None

        # 최대 3개
        picks = related[:3]

        # 채널별 언어로 댓글 작성
        headers = {
            "ko": "🔥 이것도 봐!",
            "en": "🔥 Watch these too!",
            "es": "🔥 ¡Mira estos también!",
        }
        header = headers.get(lang, headers["en"])

        lines = [header]
        for p in picks:
            lines.append(f"👉 {p['title']}")
            lines.append(f"   {p['url']}")

        return "\n".join(lines)

    except Exception as e:
        print(f"[고정 댓글] 관련 영상 조회 실패: {e}")
        return None


def _post_pinned_comment(video_id: str, text: str, channel_id: str = None):
    """댓글 작성 + 고정."""
    creds = _get_credentials(channel_id)
    if not creds:
        return

    youtube = build("youtube", "v3", credentials=creds)

    # 댓글 작성
    resp = youtube.commentThreads().insert(
        part="snippet",
        body={
            "snippet": {
                "videoId": video_id,
                "topLevelComment": {
                    "snippet": {"textOriginal": text}
                },
            }
        },
    ).execute()

    comment_id = resp["snippet"]["topLevelComment"]["id"]

    # 댓글 고정
    try:
        youtube.comments().setModerationStatus(
            id=comment_id,
            moderationStatus="published",
        ).execute()
    except Exception:
        pass  # 고정은 실패해도 댓글은 남아있음

    print(f"OK [고정 댓글] 댓글 작성 완료 (관련 영상 링크 포함)")
