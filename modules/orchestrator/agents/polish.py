"""PolishAgent — 스크립트 폴리시 + 채널 컴플라이언스.

cutter.py의 polish_scripts()를 Gemini Flash로 독립 실행.
금지 표현 필터링 + 핵심 컷 보호 포함.
"""

from __future__ import annotations

import re
import asyncio
from typing import AsyncGenerator

from modules.orchestrator.base import BaseAgent, AgentContext


class PolishAgent(BaseAgent):
    name = "PolishAgent"

    async def execute(self, ctx: AgentContext) -> AsyncGenerator[str, None]:
        from modules.gpt.cutter import polish_scripts
        from modules.utils.channel_config import get_channel_preset

        if not ctx.cuts:
            yield "WARN|[PolishAgent] 컷이 없습니다.\n"
            return

        spec = self._select_model(ctx)
        key = self._get_llm_key(ctx)
        loop = asyncio.get_running_loop()

        yield f"[PolishAgent] 스크립트 폴리시 ({spec.provider}/{spec.model_id})...\n"

        # ── 금지 표현 사전 필터링 ──
        _ch_preset = get_channel_preset(ctx.channel) if ctx.channel else None
        _forbidden = (_ch_preset or {}).get("forbidden_phrases", [])
        if _forbidden:
            self._filter_forbidden(ctx.cuts, _forbidden)

        # ── 문장 자연화 ──
        _pre_polish_hook = ctx.cuts[0].get("script", "") if ctx.cuts else ""
        _pre_polish_mid = ctx.cuts[3].get("script", "") if len(ctx.cuts) > 3 else ""
        _pre_polish_last = ctx.cuts[-1].get("script", "") if ctx.cuts else ""

        try:
            ctx.cuts, _notes = await loop.run_in_executor(None, lambda:
                polish_scripts(
                    cuts=ctx.cuts, lang=ctx.language, channel=ctx.channel,
                    llm_provider=spec.provider, api_key=key,
                    llm_model=spec.model_id,
                ))
            if _notes:
                yield "[PolishAgent] 문장 자연화 적용됨\n"
        except Exception as exc:
            yield f"WARN|[PolishAgent] 폴리시 스킵 (원본 유지): {exc}\n"

        # ── 핵심 컷 보호 (훅/리텐션/루프 약화 방지) ──
        if ctx.cuts:
            _post_hook = ctx.cuts[0].get("script", "")
            _post_mid = ctx.cuts[3].get("script", "") if len(ctx.cuts) > 3 else ""
            _post_last = ctx.cuts[-1].get("script", "")

            if _pre_polish_hook and _post_hook and len(_post_hook) > len(_pre_polish_hook) * 1.3:
                ctx.cuts[0]["script"] = _pre_polish_hook
                yield "[PolishAgent] Cut 1 훅 복원 (polish 후 길어짐)\n"

            if len(ctx.cuts) > 3 and _pre_polish_mid and _post_mid and len(_post_mid) > len(_pre_polish_mid) * 1.3:
                ctx.cuts[3]["script"] = _pre_polish_mid
                yield "[PolishAgent] Cut 4 리텐션 락 복원\n"

            _bad_endings = ["...", "사실은", "근데 진짜", "actually", "but then", "en realidad"]
            if _post_last and any(_post_last.rstrip().endswith(p) for p in _bad_endings):
                ctx.cuts[-1]["script"] = _pre_polish_last
                yield "[PolishAgent] 마지막 컷 루프 복원\n"

        # ── 금지 표현 재필터링 ──
        if _forbidden:
            self._filter_forbidden(ctx.cuts, _forbidden)

        # 스크립트 동기화
        ctx.scripts = [c.get("script", "") for c in ctx.cuts]
        self._record_estimated_llm(ctx, spec.model_id)

        yield f"[PolishAgent] 폴리시 완료. {len(ctx.cuts)}컷\n"

    def _record_estimated_llm(self, ctx: AgentContext, model_id: str) -> None:
        text_size = len(ctx.topic or "")
        for cut in ctx.cuts:
            text_size += len(cut.get("script", "") or "")
        self._tracker.record(
            self.name,
            model_id,
            input_tokens=max(1, (text_size + 3000) // 4),
            output_tokens=max(120, text_size // 4),
        )

    @staticmethod
    def _filter_forbidden(cuts: list[dict], forbidden: list[str]):
        for ci, cut in enumerate(cuts):
            scr = cut.get("script", "")
            changed = False
            for fp in forbidden:
                if fp.lower() in scr.lower():
                    scr = re.sub(re.escape(fp), "", scr, flags=re.IGNORECASE).strip()
                    scr = re.sub(r"\s{2,}", " ", scr)
                    changed = True
            if changed:
                cuts[ci]["script"] = scr
