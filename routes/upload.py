"""Upload routes — YouTube / TikTok / Instagram 업로드 및 인증 엔드포인트."""

from __future__ import annotations

import asyncio
import json
import os
import re

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["upload"])


# ── Pydantic models ─────────────────────────────────────────────────


class YouTubeUploadRequest(BaseModel):
    video_path: str = Field(..., description="업로드할 동영상 경로")
    title: str = Field(..., max_length=100)
    description: str = Field("", max_length=5000)
    tags: list[str] = Field(default_factory=list)
    privacy: str = Field("private", pattern="^(private|unlisted|public)$")
    channel_id: str | None = None
    channel: str | None = Field(None, description="채널 프리셋 이름 (채널별 client_secret 선택용)")
    publish_at: str | None = Field(None, description="예약 공개 시간 (ISO 8601, e.g. 2026-03-20T15:00:00Z)")


class TikTokUploadRequest(BaseModel):
    video_path: str = Field(..., description="업로드할 동영상 경로")
    title: str = Field(..., max_length=150)
    privacy_level: str = Field("SELF_ONLY", pattern="^(SELF_ONLY|MUTUAL_FOLLOW_FRIENDS|FOLLOWER_OF_CREATOR|PUBLIC_TO_EVERYONE)$")
    user_id: str | None = None
    channel: str | None = Field(None, description="채널 프리셋 이름")
    schedule_time: int | None = Field(None, description="예약 발행 UTC Unix timestamp (15분~75일 이내)")


class InstagramUploadRequest(BaseModel):
    video_path: str = Field(..., description="업로드할 동영상 경로")
    caption: str = Field("", max_length=2200)
    account_id: str | None = None
    channel: str | None = Field(None, description="채널 프리셋 이름")
    video_url: str | None = Field(None, description="공개 접근 가능한 영상 URL (로컬 파일 대신)")


# ── YouTube ──────────────────────────────────────────────────────────


@router.get("/youtube/status")
async def youtube_status():
    from modules.upload.youtube import get_auth_status
    return get_auth_status()


@router.post("/youtube/auth")
async def youtube_auth(req: dict = None):
    from modules.upload.youtube import create_auth_url
    try:
        channel = (req or {}).get("channel")
        url = create_auth_url(channel=channel)
        return {"auth_url": url}
    except FileNotFoundError as e:
        return {"error": str(e)}


@router.get("/youtube/callback")
async def youtube_callback(code: str, state: str | None = None):
    from modules.upload.youtube import handle_auth_callback
    from fastapi.responses import HTMLResponse
    try:
        result = handle_auth_callback(code, state)
        return HTMLResponse(
            "<html><body><h2>YouTube 연동 완료!</h2>"
            "<p>이 창을 닫고 돌아가세요.</p>"
            "<script>window.close()</script></body></html>"
        )
    except Exception as e:
        import html as _html, traceback as _tb
        _tb.print_exc()
        return HTMLResponse(f"<html><body><h2>오류</h2><p>{_html.escape(str(e))}</p><pre>{_html.escape(_tb.format_exc())}</pre></body></html>", status_code=400)


@router.post("/youtube/upload")
async def youtube_upload(req: YouTubeUploadRequest):
    from modules.upload.youtube import upload_video
    from routes.shared import cut_executor
    try:
        # 경로 보안 검증: /assets/... → assets/... (선행 슬래시 제거)
        from pathlib import Path as _P
        _vpath = req.video_path.lstrip("/")
        abs_path = os.path.abspath(os.path.realpath(_vpath))
        assets_dir = os.path.abspath(os.path.realpath("assets"))
        if not _P(abs_path).is_relative_to(assets_dir):
            return {"error": "assets 디렉토리 내의 파일만 업로드할 수 있습니다."}

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            cut_executor,
            lambda: upload_video(
                video_path=abs_path,
                title=req.title,
                description=req.description,
                tags=req.tags,
                privacy=req.privacy,
                channel_id=req.channel_id,
                publish_at=req.publish_at,
            )
        )
        return result
    except PermissionError as e:
        return {"error": str(e), "need_auth": True}
    except (FileNotFoundError, ValueError) as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"업로드 실패: {e}"}


@router.post("/youtube/disconnect")
async def youtube_disconnect():
    from modules.upload.youtube import disconnect
    return disconnect()


# ── YouTube Playlists ────────────────────────────────────────────────


@router.post("/youtube/playlists/setup/{channel}")
async def setup_playlists(channel: str):
    """채널에 카테고리별 재생목록 생성."""
    from modules.upload.youtube import ensure_playlists
    from modules.utils.channel_config import get_channel_preset
    preset = get_channel_preset(channel)
    if not preset:
        return {"success": False, "message": f"채널 '{channel}' 없음"}
    accounts_path = os.path.join("youtube_tokens", "channel_accounts.json")
    ch_id = None
    if os.path.exists(accounts_path):
        with open(accounts_path) as f:
            ch_id = json.load(f).get(channel, {}).get("youtube")
    playlists = ensure_playlists(ch_id, channel)
    return {"success": True, "channel": channel, "playlists": playlists}


@router.post("/youtube/playlists/classify/{channel}")
async def classify_channel_videos(channel: str):
    """기존 영상을 재생목록에 소급 분류."""
    from modules.upload.youtube import classify_existing_videos
    accounts_path = os.path.join("youtube_tokens", "channel_accounts.json")
    ch_id = None
    if os.path.exists(accounts_path):
        with open(accounts_path) as f:
            ch_id = json.load(f).get(channel, {}).get("youtube")
    result = await asyncio.get_running_loop().run_in_executor(
        None, lambda: classify_existing_videos(ch_id, channel)
    )
    return result


# ── TikTok ───────────────────────────────────────────────────────────


@router.get("/tiktok/status")
async def tiktok_status():
    from modules.upload.tiktok import get_auth_status
    return get_auth_status()


@router.post("/tiktok/auth")
async def tiktok_auth():
    from modules.upload.tiktok import create_auth_url
    try:
        url = create_auth_url()
        return {"auth_url": url}
    except ValueError as e:
        return {"error": str(e)}


@router.get("/tiktok/callback")
async def tiktok_callback(code: str, state: str | None = None):
    from modules.upload.tiktok import handle_auth_callback
    from fastapi.responses import HTMLResponse
    try:
        handle_auth_callback(code, state=state)
        return HTMLResponse(
            "<html><body><h2>TikTok 연동 완료!</h2>"
            "<p>이 창을 닫고 돌아가세요.</p>"
            "<script>window.close()</script></body></html>"
        )
    except Exception as e:
        import html as _html
        return HTMLResponse(f"<html><body><h2>오류</h2><p>{_html.escape(str(e))}</p></body></html>", status_code=400)


@router.post("/tiktok/upload")
async def tiktok_upload(req: TikTokUploadRequest):
    from modules.upload.tiktok import upload_video
    from routes.shared import cut_executor
    try:
        from pathlib import Path as _P
        abs_path = os.path.abspath(os.path.realpath(req.video_path))
        assets_dir = os.path.abspath(os.path.realpath("assets"))
        if not _P(abs_path).is_relative_to(assets_dir):
            return {"error": "assets 디렉토리 내의 파일만 업로드할 수 있습니다."}

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            cut_executor,
            lambda: upload_video(
                video_path=abs_path,
                title=req.title,
                privacy_level=req.privacy_level,
                user_id=req.user_id,
                schedule_time=req.schedule_time,
            )
        )
        return result
    except PermissionError as e:
        return {"error": str(e), "need_auth": True}
    except (FileNotFoundError, ValueError) as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"업로드 실패: {e}"}


@router.post("/tiktok/disconnect")
async def tiktok_disconnect():
    from modules.upload.tiktok import disconnect
    return disconnect()


# ── Instagram ────────────────────────────────────────────────────────


@router.get("/instagram/status")
async def instagram_status():
    from modules.upload.instagram import get_auth_status
    return get_auth_status()


@router.post("/instagram/auth")
async def instagram_auth():
    from modules.upload.instagram import create_auth_url
    try:
        url = create_auth_url()
        return {"auth_url": url}
    except ValueError as e:
        return {"error": str(e)}


@router.get("/instagram/callback")
async def instagram_callback(code: str, state: str | None = None):
    from modules.upload.instagram import handle_auth_callback
    from fastapi.responses import HTMLResponse
    try:
        handle_auth_callback(code, state=state)
        return HTMLResponse(
            "<html><body><h2>Instagram 연동 완료!</h2>"
            "<p>이 창을 닫고 돌아가세요.</p>"
            "<script>window.close()</script></body></html>"
        )
    except Exception as e:
        import html as _html
        return HTMLResponse(f"<html><body><h2>오류</h2><p>{_html.escape(str(e))}</p></body></html>", status_code=400)


@router.post("/instagram/upload")
async def instagram_upload(req: InstagramUploadRequest):
    from modules.upload.instagram import upload_reels
    from routes.shared import cut_executor
    try:
        from pathlib import Path as _P
        abs_path = os.path.abspath(os.path.realpath(req.video_path))
        assets_dir = os.path.abspath(os.path.realpath("assets"))
        if not _P(abs_path).is_relative_to(assets_dir):
            return {"error": "assets 디렉토리 내의 파일만 업로드할 수 있습니다."}

        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            cut_executor,
            lambda: upload_reels(
                video_path=abs_path,
                caption=req.caption,
                account_id=req.account_id,
                video_url=req.video_url,
            )
        )
        return result
    except PermissionError as e:
        return {"error": str(e), "need_auth": True}
    except FileNotFoundError as e:
        return {"error": str(e)}
    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"업로드 실패: {e}"}


@router.post("/instagram/disconnect")
async def instagram_disconnect():
    from modules.upload.instagram import disconnect
    return disconnect()


# ── 플랫폼 통합 상태 ────────────────────────────────────────────────


@router.get("/upload/platforms")
async def upload_platforms():
    """모든 업로드 플랫폼의 연동 상태를 한번에 반환합니다."""
    from modules.upload.youtube import get_auth_status as yt_status
    from modules.upload.tiktok import get_auth_status as tt_status
    from modules.upload.instagram import get_auth_status as ig_status
    return {
        "youtube": yt_status(),
        "tiktok": tt_status(),
        "instagram": ig_status(),
    }
