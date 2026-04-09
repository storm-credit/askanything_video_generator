"""RenderAgent — Remotion 렌더링 + 썸네일 생성.

LLM 호출 없음. 실패 시 최대 2회 리트라이.
"""

from __future__ import annotations

import os
import asyncio
import time
from typing import AsyncGenerator

from modules.orchestrator.base import BaseAgent, AgentContext

MAX_RETRIES = 2
RETRY_DELAY = 15  # 초 (메모리/프로세스 정리 대기)


class RenderAgent(BaseAgent):
    name = "RenderAgent"

    async def execute(self, ctx: AgentContext) -> AsyncGenerator[str, None]:
        from modules.video.remotion import create_remotion_video

        if not ctx.visual_paths or not ctx.audio_paths:
            yield "ERROR|[RenderAgent] 이미지 또는 오디오가 없습니다.\n"
            return

        # 실패한 컷 체크
        failed_visual = [i+1 for i, p in enumerate(ctx.visual_paths) if p is None]
        failed_audio = [i+1 for i, p in enumerate(ctx.audio_paths) if p is None]
        if failed_visual or failed_audio:
            details = []
            if failed_visual:
                details.append(f"이미지 실패: 컷 {failed_visual}")
            if failed_audio:
                details.append(f"오디오 실패: 컷 {failed_audio}")
            yield f"ERROR|[RenderAgent] 소스 누락: {', '.join(details)}\n"
            return

        platform_label = ", ".join(p.upper() for p in ctx.platforms)
        descriptions = [cut.get("description", "") for cut in ctx.cuts]
        loop = asyncio.get_running_loop()

        # 최대 MAX_RETRIES회 리트라이
        render_result = None
        for attempt in range(MAX_RETRIES + 1):
            if attempt > 0:
                yield f"[RenderAgent] 리트라이 {attempt}/{MAX_RETRIES} ({RETRY_DELAY}초 후)...\n"
                await asyncio.sleep(RETRY_DELAY)

            yield f"[RenderAgent] Remotion 렌더링 시작 — {platform_label}\n"

            try:
                render_result = await loop.run_in_executor(
                    None,
                    lambda: create_remotion_video(
                        ctx.visual_paths, ctx.audio_paths, ctx.scripts,
                        ctx.word_timestamps, ctx.topic_folder,
                        title=ctx.title,
                        camera_style=ctx.camera_style,
                        bgm_theme=ctx.bgm_theme,
                        channel=ctx.channel,
                        platforms=ctx.platforms,
                        caption_size=ctx.caption_size,
                        caption_y=ctx.caption_y,
                        descriptions=descriptions,
                    ),
                )
            except Exception as exc:
                yield f"WARN|[RenderAgent] 렌더링 예외: {str(exc)[:100]}\n"
                render_result = None

            if render_result:
                break
            elif attempt < MAX_RETRIES:
                yield f"WARN|[RenderAgent] 렌더링 실패 — 리트라이 예정\n"

        if not render_result:
            yield "ERROR|[RenderAgent] Remotion 렌더링 실패 (리트라이 소진).\n"
            return

        # 결과 정규화
        if isinstance(render_result, str):
            ctx.video_paths = {"youtube": render_result}
        else:
            ctx.video_paths = render_result

        # 썸네일 자동 생성
        try:
            from modules.utils.thumbnail import select_best_thumbnail, create_thumbnail
            best_img = select_best_thumbnail(ctx.visual_paths)
            if best_img:
                thumb_dir = os.path.join("assets", ctx.topic_folder, "video")
                thumb_output = os.path.join(thumb_dir, "thumbnail.jpg")
                ctx.thumbnail_path = create_thumbnail(best_img, thumb_output)
        except Exception as exc:
            print(f"[RenderAgent] 썸네일 생성 경고: {exc}")

        primary = list(ctx.video_paths.keys())[0]
        yield f"[RenderAgent] 렌더링 완료. {len(ctx.video_paths)}개 플랫폼\n"
