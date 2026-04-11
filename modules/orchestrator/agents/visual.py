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

            # 비주얼 디렉터 후 주제 일치 재검증 (무관 피사체 방지)
            ctx.cuts = await loop.run_in_executor(None, lambda:
                _verify_subject_match(ctx.cuts, topic_title,
                    spec.provider, key, ctx.language, spec.model_id))

            yield f"[VisualDirectorAgent] 이미지 프롬프트 강화 완료\n"
        except Exception as exc:
            yield f"WARN|[VisualDirectorAgent] 스킵 (원본 유지): {exc}\n"
