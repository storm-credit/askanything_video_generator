"""QualityAgent — 구조/팩트/주제 일치 + 코드 HARD FAIL 검증."""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from modules.orchestrator.base import BaseAgent, AgentContext


class QualityAgent(BaseAgent):
    name = "QualityAgent"

    async def execute(self, ctx: AgentContext) -> AsyncGenerator[str, None]:
        from modules.gpt.cutter import (
            _verify_facts, _verify_highness_structure, _verify_subject_match,
            _validate_hard_fail, _validate_region_style,
        )
        from modules.gpt.cutter.generator import _should_run_fact_verify

        if not ctx.cuts:
            yield "WARN|[QualityAgent] 검증할 컷이 없습니다.\n"
            return

        spec = self._select_model(ctx)
        key = self._get_llm_key(ctx)
        loop = asyncio.get_running_loop()
        topic_title = ctx.topic.split("\n\n[원본 영상 내용]")[0].strip()

        yield f"[QualityAgent] 전문가 검증 시작 ({spec.provider}/{spec.model_id})...\n"

        # ① 구조 검증: 컷1 훅 + 마지막 루프만 전문 점검/수정
        yield "[QualityAgent] 구조 검증: 컷1 훅 + 마지막 루프...\n"
        ctx.cuts = await loop.run_in_executor(None, lambda:
            _verify_highness_structure(
                ctx.cuts, topic_title, spec.provider, key,
                ctx.language, spec.model_id, ctx.channel,
            ))
        self._record_estimated_llm(ctx, spec.model_id, "structure")

        # ② 팩트 검증: 고위험 포맷/키워드 + fact_context 있을 때만
        if _should_run_fact_verify(topic_title, ctx.format_type, ctx.fact_context):
            yield "[QualityAgent] 팩트 검증: 고위험 포맷/수치 주장 확인...\n"
            ctx.cuts = await loop.run_in_executor(None, lambda:
                _verify_facts(
                    ctx.cuts, ctx.fact_context, topic_title,
                    spec.provider, key, ctx.language, spec.model_id,
                ))
            self._record_estimated_llm(ctx, spec.model_id, "facts")
        elif ctx.fact_context:
            yield "[QualityAgent] 팩트 검증 스킵: 저위험 포맷/주제\n"

        # ③ 주제-이미지 일치 검증: 구조/팩트 수정 후 최종 script 기준으로 prompt 보정
        yield "[QualityAgent] script↔image 주제 일치 검증...\n"
        ctx.cuts = await loop.run_in_executor(None, lambda:
            _verify_subject_match(ctx.cuts, topic_title,
                spec.provider, key, ctx.language, spec.model_id))
        self._record_estimated_llm(ctx, spec.model_id, "subject")

        # ④ HARD FAIL 검증 (코드만 — LLM 불필요)
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

    def _record_estimated_llm(self, ctx: AgentContext, model_id: str, phase: str) -> None:
        """Verifier helpers do not expose usage metadata yet, so record a conservative estimate."""
        text_size = len(ctx.topic or "") + len(ctx.fact_context or "")
        for cut in ctx.cuts:
            text_size += len(cut.get("script", "") or "")
            text_size += len(cut.get("prompt", "") or "")
            text_size += len(cut.get("description", "") or cut.get("text", "") or "")
        phase_overhead = {"structure": 1800, "facts": 2200, "subject": 2000}.get(phase, 1800)
        output_tokens = max(120, len(ctx.cuts) * 55)
        self._tracker.record(
            self.name,
            model_id,
            input_tokens=max(1, (text_size + phase_overhead) // 4),
            output_tokens=output_tokens,
        )
