"""VideoAgent — 이미지→영상 변환 (Veo3/Kling/Sora2).

ImageAgent가 생성한 정지 이미지를 영상으로 변환.
히어로 컷(SHOCK/REVEAL)만 변환하거나 전체 변환 선택 가능.
LLM 호출 없음.
"""

from __future__ import annotations

import os
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncGenerator

from modules.orchestrator.base import BaseAgent, AgentContext


class VideoAgent(BaseAgent):
    """이미지→영상 변환 에이전트."""

    name = "VideoAgent"

    async def execute(self, ctx: AgentContext) -> AsyncGenerator[str, None]:
        from modules.video.engines import generate_video_from_image, check_engine_available
        from modules.utils.keys import get_google_key

        if ctx.video_engine == "none":
            yield "[VideoAgent] 비디오 엔진 없음 — Ken Burns 모드\n"
            return

        if not ctx.visual_paths:
            yield "WARN|[VideoAgent] 이미지가 없습니다.\n"
            return

        # 엔진 사전 검증
        google_key = get_google_key(ctx.llm_key, service=ctx.video_engine,
                                    extra_keys=ctx.gemini_keys_override)
        engine_ok, reason = check_engine_available(ctx.video_engine, google_key)
        if not engine_ok:
            yield f"WARN|[VideoAgent] {ctx.video_engine}: {reason} — Ken Burns 대체\n"
            return

        # 히어로 컷 판별: SHOCK/REVEAL만 영상 변환 (비용 절감)
        hero_emotions = {"SHOCK", "REVEAL"}
        hero_mode = ctx.video_model == "hero-only"

        if hero_mode:
            hero_indices = set()
            for i, cut in enumerate(ctx.cuts):
                desc = cut.get("description", cut.get("text", ""))
                if any(f"[{e}]" in desc for e in hero_emotions):
                    hero_indices.add(i)
            skip_count = len(ctx.cuts) - len(hero_indices)
            yield f"[VideoAgent] 히어로 모드: {len(hero_indices)}컷만 영상 변환 ({skip_count}컷 Ken Burns)\n"
        else:
            hero_indices = set(range(len(ctx.cuts)))
            yield f"[VideoAgent] 전체 {len(ctx.cuts)}컷 영상 변환 ({ctx.video_engine})...\n"

        def _find_existing_video(i: int) -> str | None:
            """video_clips/ 폴더에 기존 Veo3 영상이 있으면 재사용."""
            clips_dir = os.path.join("assets", ctx.topic_folder, "video_clips")
            if not os.path.isdir(clips_dir):
                return None
            # veo3_cut_00.mp4, veo3_cut_01.mp4 패턴
            for pattern in [f"veo3_cut_{i:02d}.mp4", f"cut_{i:02d}.mp4"]:
                path = os.path.join(clips_dir, pattern)
                if os.path.exists(path) and os.path.getsize(path) > 10000:  # 10KB 이상
                    return path
            return None

        def _convert_one(i: int) -> tuple[int, str | None]:
            if ctx.is_cancelled():
                return i, None

            img_path = ctx.visual_paths[i]
            if not img_path or not os.path.exists(img_path):
                return i, None

            if i not in hero_indices:
                return i, None  # Ken Burns (이미지 그대로)

            # 기존 Veo3 영상 재사용
            existing = _find_existing_video(i)
            if existing:
                print(f"[VideoAgent] 컷 {i+1} 기존 영상 재사용: {os.path.basename(existing)}")
                return i, existing

            try:
                vid_key = get_google_key(ctx.llm_key, service=ctx.video_engine,
                                        extra_keys=ctx.gemini_keys_override)
                cut = ctx.cuts[i] if i < len(ctx.cuts) else {}
                result = generate_video_from_image(
                    img_path,
                    cut.get("prompt", ""),
                    i, ctx.topic_folder,
                    ctx.video_engine,
                    vid_key,
                    description=cut.get("description", ""),
                    veo_model=ctx.video_model if ctx.video_model != "hero-only" else None,
                    gemini_api_keys=ctx.gemini_keys_override,
                )
                return i, result
            except Exception as exc:
                print(f"[VideoAgent] 컷 {i+1} 변환 실패: {exc}")
                return i, None

        executor = ThreadPoolExecutor(max_workers=2)  # 비디오는 무겁기 때문에 2개로 제한
        loop = asyncio.get_running_loop()
        tasks = [loop.run_in_executor(executor, _convert_one, i)
                 for i in range(len(ctx.visual_paths))]

        converted = 0
        for coro in asyncio.as_completed(tasks):
            i, vid_path = await coro
            if vid_path:
                ctx.visual_paths[i] = vid_path  # 이미지를 영상으로 교체
                converted += 1
                ctx.video_count += 1
                yield f"  -> 컷 {i+1} 영상 변환 완료\n"

        executor.shutdown(wait=False)

        if converted > 0:
            yield f"[VideoAgent] {converted}컷 영상 변환 완료\n"
        else:
            yield "[VideoAgent] 영상 변환 없음 — 정지 이미지 사용\n"
