"""ImageAgent — 병렬 이미지 생성 + 폴백 체인.

api_server.py의 process_cut() 이미지 로직을 래핑.
LLM 호출 없음 — Imagen/Nano Banana/DALL-E 좌표만.
"""

from __future__ import annotations

import os
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncGenerator

from modules.orchestrator.base import BaseAgent, AgentContext


class ImageAgent(BaseAgent):
    name = "ImageAgent"

    async def execute(self, ctx: AgentContext) -> AsyncGenerator[str, None]:
        from modules.image.imagen import generate_image_imagen, generate_image_nano_banana
        from modules.image.dalle import generate_image as generate_image_dalle
        from modules.utils.keys import get_google_key

        if not ctx.cuts:
            yield "WARN|[ImageAgent] 컷이 없습니다.\n"
            return

        ctx.visual_paths = [None] * len(ctx.cuts)
        ctx.cut1_ab_variants = []

        image_label = "Imagen 4" if ctx.image_engine == "imagen" else "DALL-E"
        yield f"[ImageAgent] {len(ctx.cuts)}컷 이미지 생성 시작 ({image_label})...\n"

        image_semaphore = threading.Semaphore(3)

        def _get_image_key():
            if ctx.image_engine in ("imagen", "nano_banana"):
                return get_google_key(ctx.llm_key, service="imagen",
                                      extra_keys=ctx.gemini_keys_override)
            return ctx.api_key_override

        def _generate_one(i: int, cut: dict) -> tuple[int, str | None, list[str]]:
            if ctx.is_cancelled():
                return i, None, []

            img_path = None
            ab_variants: list[str] = []

            with image_semaphore:
                try:
                    key = _get_image_key()
                    if ctx.image_engine == "imagen":
                        img_path = generate_image_imagen(
                            cut["prompt"], i, ctx.topic_folder, key,
                            model_override=ctx.image_model,
                            gemini_api_keys=ctx.gemini_keys_override,
                            topic=ctx.topic)
                    elif ctx.image_engine == "nano_banana":
                        img_path = generate_image_nano_banana(
                            cut["prompt"], i, ctx.topic_folder, key,
                            gemini_api_keys=ctx.gemini_keys_override,
                            topic=ctx.topic)
                    else:
                        img_path = generate_image_dalle(
                            cut["prompt"], i, ctx.topic_folder, key,
                            topic=ctx.topic)
                except Exception as exc:
                    # image_model이 명시적으로 지정된 경우 폴백 없이 에러 처리
                    if ctx.image_model:
                        print(f"[ImageAgent] 컷 {i+1} {ctx.image_model} 실패 (폴백 없음): {exc}")
                    # 폴백 체인: Imagen → Nano Banana → DALL-E (model 미지정 시에만)
                    elif ctx.image_engine in ("imagen", "nano_banana"):
                        if ctx.image_engine == "imagen":
                            try:
                                nb_key = get_google_key(ctx.llm_key, service="nano_banana",
                                                        extra_keys=ctx.gemini_keys_override)
                                img_path = generate_image_nano_banana(
                                    cut["prompt"], i, ctx.topic_folder, nb_key,
                                    gemini_api_keys=ctx.gemini_keys_override,
                                    topic=ctx.topic)
                            except Exception:
                                pass
                        if not img_path:
                            dalle_key = ctx.api_key_override or os.getenv("OPENAI_API_KEY")
                            if dalle_key:
                                try:
                                    img_path = generate_image_dalle(
                                        cut["prompt"], i, ctx.topic_folder, dalle_key,
                                        topic=ctx.topic)
                                except Exception:
                                    print(f"[ImageAgent] 컷 {i+1} 전체 폴백 실패")
                    else:
                        print(f"[ImageAgent] 컷 {i+1} 이미지 생성 실패: {exc}")

            # 컷1 A/B 테스트 변형
            if i == 0 and img_path:
                variant_suffixes = [
                    ", extreme close-up shot, macro perspective, filling the entire frame, shallow depth of field",
                    ", ultra wide establishing shot, tiny human silhouette for scale comparison, dramatic deep perspective",
                ]
                for vi, suffix in enumerate(variant_suffixes):
                    try:
                        vkey = _get_image_key()
                        vprompt = cut["prompt"].rstrip(". ,") + suffix
                        vidx = 100 + vi
                        if ctx.image_engine == "imagen":
                            vp = generate_image_imagen(
                                vprompt, vidx, ctx.topic_folder, vkey,
                                model_override=ctx.image_model,
                                gemini_api_keys=ctx.gemini_keys_override,
                                topic=ctx.topic)
                        elif ctx.image_engine == "nano_banana":
                            vp = generate_image_nano_banana(
                                vprompt, vidx, ctx.topic_folder, vkey,
                                gemini_api_keys=ctx.gemini_keys_override,
                                topic=ctx.topic)
                        else:
                            vp = generate_image_dalle(
                                vprompt, vidx, ctx.topic_folder, vkey,
                                topic=ctx.topic)
                        if vp:
                            ab_variants.append(vp)
                    except Exception:
                        pass

            return i, img_path, ab_variants

        executor = ThreadPoolExecutor(max_workers=4)
        loop = asyncio.get_running_loop()
        tasks = [loop.run_in_executor(executor, _generate_one, i, cut)
                 for i, cut in enumerate(ctx.cuts)]

        for coro in asyncio.as_completed(tasks):
            i, path, ab_vars = await coro
            ctx.visual_paths[i] = path
            if i == 0 and ab_vars:
                ctx.cut1_ab_variants = ab_vars
            status = "OK" if path else "FAILED"
            yield f"  -> 컷 {i+1} 이미지 {status}\n"

        executor.shutdown(wait=False)

        failed = [i+1 for i, p in enumerate(ctx.visual_paths) if p is None]
        if failed:
            yield f"WARN|[ImageAgent] 이미지 실패: 컷 {failed}\n"
        else:
            yield f"[ImageAgent] 전체 {len(ctx.cuts)}컷 이미지 생성 완료\n"
