"""QualityAgent — 경량 검증 (주제 일치 + 코드 HARD FAIL만).

LLM 호출 1회만 (주제-이미지 일치). 나머지는 코드 레벨 검증.
하이네스 구조/팩트 검증/학술체 리라이트는 프롬프트가 이미 강제하므로 제거.
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from modules.orchestrator.base import BaseAgent, AgentContext


class QualityAgent(BaseAgent):
    name = "QualityAgent"

    async def execute(self, ctx: AgentContext) -> AsyncGenerator[str, None]:
        from modules.gpt.cutter import (
            _verify_subject_match, _validate_hard_fail, _validate_region_style,
        )

        if not ctx.cuts:
            yield "WARN|[QualityAgent] 검증할 컷이 없습니다.\n"
            return

        spec = self._select_model(ctx)
        key = self._get_llm_key(ctx)
        loop = asyncio.get_running_loop()
        topic_title = ctx.topic.split("\n\n[원본 영상 내용]")[0].strip()

        # ① 주제-이미지 일치 검증 (LLM 1회 — 유일한 LLM 호출)
        yield f"[QualityAgent] script↔image 주제 일치 검증 ({spec.model_id})...\n"
        ctx.cuts = await loop.run_in_executor(None, lambda:
            _verify_subject_match(ctx.cuts, topic_title,
                spec.provider, key, ctx.language, spec.model_id))

        # ② HARD FAIL 검증 (코드만 — LLM 불필요, 무료)
        for cut in ctx.cuts:
            cut.setdefault("format_type", ctx.format_type or "")
            cut.setdefault("topic", topic_title)
            cut.setdefault("topic_title", topic_title)
        hard_fails = _validate_hard_fail(ctx.cuts, ctx.channel)
        region_warns = _validate_region_style(ctx.cuts, ctx.channel)

        if hard_fails:
            setattr(ctx, "quality_hard_fails", hard_fails)
            yield f"WARN|[QualityAgent] {len(hard_fails)}개 HARD FAIL 감지\n"
            for f in hard_fails:
                yield f"WARN|  - {f}\n"
        else:
            setattr(ctx, "quality_hard_fails", [])
        if region_warns:
            yield f"WARN|[QualityAgent] {len(region_warns)}개 지역 스타일 경고\n"
        if not hard_fails and not region_warns:
            yield "[QualityAgent] 검증 통과\n"

        ctx.scripts = [c.get("script", "") for c in ctx.cuts]
