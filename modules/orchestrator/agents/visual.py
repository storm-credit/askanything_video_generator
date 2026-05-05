"""VisualDirectorAgent — 이미지 프롬프트 전문 리라이트.

cutter.py의 _enhance_image_prompts()를 Gemini Flash로 독립 실행.
컷1 특별 강화 + 주제 일치 재검증 포함.
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from modules.orchestrator.base import BaseAgent, AgentContext


class VisualDirectorAgent(BaseAgent):
    name = "VisualDirectorAgent"

    async def execute(self, ctx: AgentContext) -> AsyncGenerator[str, None]:
        from modules.gpt.cutter import _enhance_image_prompts, _verify_subject_match
        from modules.gpt.cutter.enhancer import ensure_visual_prompts_in_english

        if not ctx.cuts:
            yield "WARN|[VisualDirectorAgent] 컷이 없습니다.\n"
            return

        spec = self._select_model(ctx)
        key = self._get_llm_key(ctx)
        loop = asyncio.get_running_loop()
        topic_title = ctx.topic.split("\n\n[원본 영상 내용]")[0].strip()

        yield f"[VisualDirectorAgent] 이미지 프롬프트 리라이트 ({spec.provider}/{spec.model_id})...\n"

        try:
            ctx.cuts = await loop.run_in_executor(None, lambda:
                _enhance_image_prompts(ctx.cuts, topic_title,
                    ctx.language, key, ctx.channel, ctx.format_type))

            ctx.cuts = await loop.run_in_executor(None, lambda:
                ensure_visual_prompts_in_english(
                    ctx.cuts,
                    topic_title,
                    key,
                    ctx.channel,
                    ctx.format_type,
                ))

            # 비주얼 디렉터 후 주제 일치 재검증 (무관 피사체 방지)
            ctx.cuts = await loop.run_in_executor(None, lambda:
                _verify_subject_match(ctx.cuts, topic_title,
                    spec.provider, key, ctx.language, spec.model_id))

            ctx.cuts = await loop.run_in_executor(None, lambda:
                ensure_visual_prompts_in_english(
                    ctx.cuts,
                    topic_title,
                    key,
                    ctx.channel,
                    ctx.format_type,
                ))

            yield f"[VisualDirectorAgent] 이미지 프롬프트 강화 완료\n"
            self._record_estimated_llm(ctx, spec.model_id)
        except Exception as exc:
            yield f"WARN|[VisualDirectorAgent] 스킵 (원본 유지): {exc}\n"

    def _record_estimated_llm(self, ctx: AgentContext, model_id: str) -> None:
        text_size = len(ctx.topic or "")
        for cut in ctx.cuts:
            text_size += len(cut.get("script", "") or "")
            text_size += len(cut.get("prompt", "") or "")
            text_size += len(cut.get("description", "") or cut.get("text", "") or "")
        self._tracker.record(
            self.name,
            model_id,
            input_tokens=max(1, (text_size * 2 + 5000) // 4),
            output_tokens=max(200, text_size // 5),
        )
