"""UploadAgent — 멀티 플랫폼 업로드 (YouTube/TikTok/Instagram).

LLM 호출 없음.
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from modules.orchestrator.base import BaseAgent, AgentContext


class UploadAgent(BaseAgent):
    name = "UploadAgent"

    async def execute(self, ctx: AgentContext) -> AsyncGenerator[str, None]:
        import os
        import re
        from modules.utils.channel_config import get_channel_preset, get_upload_account

        if not ctx.channel or ctx.publish_mode == "local":
            yield "[UploadAgent] 로컬 모드 — 업로드 생략\n"
            return

        if not ctx.video_paths:
            yield "WARN|[UploadAgent] 업로드할 영상이 없습니다.\n"
            return

        upload_preset = get_channel_preset(ctx.channel)
        upload_platforms = upload_preset.get("platforms", []) if upload_preset else []

        if not upload_platforms:
            yield "[UploadAgent] 업로드 플랫폼 미설정 — 생략\n"
            return

        # privacy 매핑
        if ctx.publish_mode == "realtime":
            yt_privacy, tt_privacy = "public", "PUBLIC_TO_EVERYONE"
        elif ctx.publish_mode == "private":
            yt_privacy, tt_privacy = "private", "SELF_ONLY"
        else:  # scheduled
            yt_privacy, tt_privacy = "private", "SELF_ONLY"

        # 예약 시간 파싱
        yt_publish_at = None
        tt_schedule_time = None
        if ctx.publish_mode == "scheduled" and ctx.scheduled_time:
            from datetime import datetime, timezone
            try:
                sched_dt = datetime.fromisoformat(ctx.scheduled_time)
                if sched_dt.tzinfo is None:
                    sched_dt = sched_dt.replace(tzinfo=timezone.utc)
                yt_publish_at = sched_dt.isoformat()
                tt_schedule_time = int(sched_dt.timestamp())
            except ValueError:
                yield f"WARN|예약 시간 형식 오류: {ctx.scheduled_time}\n"

        primary_platform = list(ctx.video_paths.keys())[0]
        abs_video_path = os.path.abspath(ctx.video_paths[primary_platform])
        loop = asyncio.get_running_loop()
        ctx.upload_results = []

        for plat in upload_platforms:
            account_id = get_upload_account(ctx.channel, plat)
            try:
                if plat == "youtube":
                    from modules.upload.youtube import upload_video as yt_upload
                    yield f"[UploadAgent] YouTube 업로드 시작... ({yt_privacy})\n"
                    # description: LLM 생성 설명 우선, 없으면 스크립트 요약
                    _yt_desc = ctx.description if ctx.description else "\n".join(s.strip() for s in ctx.scripts[:3] if s.strip())
                    # 태그: 콘텐츠 태그 우선, 채널/언어는 빈 슬롯에만
                    _content_tags = [t.lstrip("#") for t in (ctx.tags or [])][:3]
                    _extra_tags = [ctx.channel, ctx.language]
                    _yt_tags = (_content_tags + [t for t in _extra_tags if t])[:5]
                    yt_result = await loop.run_in_executor(
                        None,
                        lambda: yt_upload(
                            video_path=abs_video_path,
                            title=ctx.title,
                            description=_yt_desc,
                            tags=_yt_tags,
                            privacy=yt_privacy,
                            channel_id=account_id,
                            publish_at=yt_publish_at,
                            format_type=ctx.format_type,
                            series_title=ctx.series_title,
                            series_id=ctx.series_id,
                            channel=ctx.channel or "",
                        ),
                    )
                    if yt_result.get("success"):
                        url = yt_result.get("url", "")
                        sched_info = f" (예약: {yt_publish_at})" if yt_publish_at else ""
                        yield f"UPLOAD_DONE|youtube|{url}{sched_info}\n"
                        ctx.upload_results.append({"platform": "youtube", "url": url})
                    else:
                        yield f"WARN|YouTube 업로드 실패: {yt_result.get('error', 'unknown')}\n"

                elif plat == "tiktok":
                    from modules.upload.tiktok import upload_video as tt_upload
                    yield f"[UploadAgent] TikTok 업로드 시작...\n"
                    tt_result = await loop.run_in_executor(
                        None,
                        lambda: tt_upload(
                            video_path=abs_video_path,
                            title=ctx.title[:150],
                            privacy_level=tt_privacy,
                            user_id=account_id,
                            schedule_time=tt_schedule_time,
                        ),
                    )
                    if tt_result.get("success"):
                        yield f"UPLOAD_DONE|tiktok|\n"
                        ctx.upload_results.append({"platform": "tiktok"})
                    else:
                        yield f"WARN|TikTok 업로드 실패\n"

            except PermissionError:
                yield f"WARN|{plat.upper()} 인증 필요 — 설정에서 계정을 연동해주세요\n"
            except Exception as upload_err:
                safe_err = re.sub(
                    r"(AIza|sk-|key=|token=|Bearer )[A-Za-z0-9_\-]{4,}",
                    r"\1***", str(upload_err)[:150])
                yield f"WARN|{plat.upper()} 업로드 실패: {safe_err}\n"

        if ctx.upload_results:
            yield f"[UploadAgent] {len(ctx.upload_results)}개 플랫폼 업로드 완료\n"
