"""ScriptAgent — 대본 생성 (Phase 1 only).

generate_cuts()를 _skip_verify=True, _skip_visual_director=True, _skip_polish=True로 호출.
LLM 호출 + 파싱 + 컷 수 조정까지만 실행.
검증/비주얼디렉터/폴리시는 각 전문 에이전트가 담당.
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from modules.orchestrator.base import BaseAgent, AgentContext


class ScriptAgent(BaseAgent):
    name = "ScriptAgent"

    async def execute(self, ctx: AgentContext) -> AsyncGenerator[str, None]:
        from modules.gpt.cutter import generate_cuts

        spec = self._select_model(ctx)
        topic_preview = ctx.topic.split(chr(10))[0][:50]
        yield f"[ScriptAgent] '{topic_preview}' 기획 시작... ({spec.provider}/{spec.model_id})\n"

        loop = asyncio.get_running_loop()
        # Vertex AI 모드: SA 인증 사용 → API 키 불필요
        import os
        if os.getenv("GEMINI_BACKEND") == "vertex_ai" and spec.provider == "gemini":
            key = None
        else:
            key = self._get_llm_key(ctx)

        # Phase 1 only: 검증/비주얼/폴리시 스킵 → 에이전트별 독립 실행
        result = await loop.run_in_executor(
            None,
            lambda: generate_cuts(
                ctx.topic,
                api_key_override=ctx.api_key_override,
                lang=ctx.language,
                llm_provider=spec.provider,
                llm_key_override=key,
                channel=ctx.channel,
                llm_model=spec.model_id,
                reference_url=ctx.reference_url,
                format_type=ctx.format_type,
                series_title=ctx.series_title,
                series_context=self._build_series_context(ctx),
                _skip_verify=True,
                _skip_visual_director=True,
                _skip_polish=True,
            ),
        )

        # skip 모드: 6개 값 반환 (cuts, folder, title, tags, desc, fact_context)
        cuts, topic_folder, title, tags, desc, fact_context = result

        # 테스트 모드: 컷 수 제한
        if ctx.max_cuts and len(cuts) > ctx.max_cuts:
            cuts = cuts[:ctx.max_cuts]
            yield f"[ScriptAgent] 테스트 모드: {ctx.max_cuts}컷으로 제한\n"

        # 컨텍스트에 결과 기록
        ctx.cuts = cuts
        detected_format = next(
            (str(c.get("format_type", "")).upper() for c in cuts if c.get("format_type")),
            "",
        )
        if detected_format:
            ctx.format_type = detected_format
        ctx.topic_folder = topic_folder
        ctx.title = title
        ctx.tags = tags
        ctx.description = desc
        ctx.fact_context = fact_context
        ctx.scripts = [c.get("script", "") for c in cuts]
        self._record_estimated_llm(ctx, spec.model_id)

        yield f"[ScriptAgent] {len(cuts)}컷 기획 완료. '{title}'\n"

    def _build_series_context(self, ctx: AgentContext) -> str | None:
        fmt = (ctx.format_type or "").upper()
        if fmt != "WHO_WINS" and not ctx.series_title:
            return None
        lines = [
            "current_topic: " + (ctx.topic.split(chr(10))[0].strip() or ctx.topic[:120]),
        ]
        if ctx.series_title:
            lines.insert(0, f"series_title: {ctx.series_title}")
        if ctx.series_id:
            lines.append(f"series_id: {ctx.series_id}")
        try:
            from modules.utils.series_state import build_series_episode_context

            state_context = build_series_episode_context(ctx.series_title, ctx.topic, ctx.format_type)
            if state_context:
                lines.append(state_context)
        except Exception:
            pass
        lines.append(
            "continuity_rule: keep the VS/tournament running; use this matchup as the current episode and tease the next challenger in the final cut."
        )
        return "\n".join(lines)

    def _record_estimated_llm(self, ctx: AgentContext, model_id: str) -> None:
        text_size = len(ctx.topic or "") + len(ctx.fact_context or "") + len(ctx.title or "") + len(ctx.description or "")
        for cut in ctx.cuts:
            text_size += len(cut.get("script", "") or "")
            text_size += len(cut.get("prompt", "") or "")
            text_size += len(cut.get("description", "") or cut.get("text", "") or "")
        self._tracker.record(
            self.name,
            model_id,
            input_tokens=max(1, (len(ctx.topic or "") + 14000) // 4),
            output_tokens=max(300, text_size // 4),
        )
