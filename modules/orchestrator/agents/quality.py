"""QualityAgent — 5단계 검증 파이프라인.

cutter.py의 검증 함수들을 Gemini Flash로 독립 실행:
  ① _verify_highness_structure (Hook/충격체인/루프엔딩)
  ② _verify_subject_match (script↔image_prompt 일치)
  ③ _verify_facts (팩트 검증)
  ④ _validate_hard_fail (코드 레벨 품질 게이트)
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator

from modules.orchestrator.base import BaseAgent, AgentContext


class QualityAgent(BaseAgent):
    name = "QualityAgent"

    async def execute(self, ctx: AgentContext) -> AsyncGenerator[str, None]:
        from modules.gpt.cutter import (
            _verify_highness_structure, _verify_subject_match,
            _verify_facts, _validate_hard_fail, _validate_region_style,
            _rewrite_academic_tone,
        )

        if not ctx.cuts:
            yield "WARN|[QualityAgent] 검증할 컷이 없습니다.\n"
            return

        spec = self._select_model(ctx)
        key = self._get_llm_key(ctx)
        loop = asyncio.get_running_loop()
        topic_title = ctx.topic.split("\n\n[원본 영상 내용]")[0].strip()

        yield f"[QualityAgent] {len(ctx.cuts)}컷 검증 시작 ({spec.provider}/{spec.model_id})...\n"

        # ① 하이네스 구조 검증
        yield "[QualityAgent] ① Hook/충격체인/루프엔딩 구조 검증...\n"
        _scripts_before = [c["script"] for c in ctx.cuts]
        ctx.cuts = await loop.run_in_executor(None, lambda:
            _verify_highness_structure(ctx.cuts, topic_title,
                spec.provider, key, ctx.language, spec.model_id, ctx.channel))

        # ② 주제-이미지 일치 검증
        yield "[QualityAgent] ② script↔image_prompt 주제 일치 검증...\n"
        ctx.cuts = await loop.run_in_executor(None, lambda:
            _verify_subject_match(ctx.cuts, topic_title,
                spec.provider, key, ctx.language, spec.model_id))

        # ②-b 구조 수정이 스크립트를 바꿨으면 재검증 1회
        _scripts_after = [c["script"] for c in ctx.cuts]
        if _scripts_before != _scripts_after:
            yield "[QualityAgent] ②-b 스크립트 변경 감지 → 주제 재검증\n"
            ctx.cuts = await loop.run_in_executor(None, lambda:
                _verify_subject_match(ctx.cuts, topic_title,
                    spec.provider, key, ctx.language, spec.model_id))

        # ③ 팩트 검증
        if ctx.fact_context:
            yield "[QualityAgent] ③ 팩트 검증...\n"
            ctx.cuts = await loop.run_in_executor(None, lambda:
                _verify_facts(ctx.cuts, ctx.fact_context, topic_title,
                    spec.provider, key, ctx.language, spec.model_id))

        # ④ HARD FAIL 검증 (코드 레벨)
        hard_fails = _validate_hard_fail(ctx.cuts, ctx.channel)
        region_warns = _validate_region_style(ctx.cuts, ctx.channel)

        if hard_fails:
            yield f"[QualityAgent] ④ {len(hard_fails)}개 HARD FAIL — 자동 수정 시도...\n"
            has_academic = any("ACADEMIC" in f for f in hard_fails)
            has_structure = any(k in "".join(hard_fails) for k in ["HOOK", "TENSION", "LOOP", "TONE"])
            has_visual = any("VISUAL" in f for f in hard_fails)

            if has_academic:
                ctx.cuts = await loop.run_in_executor(None, lambda:
                    _rewrite_academic_tone(ctx.cuts, ctx.language,
                        spec.provider, key, spec.model_id))
            if has_structure:
                ctx.cuts = await loop.run_in_executor(None, lambda:
                    _verify_highness_structure(ctx.cuts, topic_title,
                        spec.provider, key, ctx.language, spec.model_id, ctx.channel))
            if has_visual:
                ctx.cuts = await loop.run_in_executor(None, lambda:
                    _verify_subject_match(ctx.cuts, topic_title,
                        spec.provider, key, ctx.language, spec.model_id))

            # 재검증
            remaining = _validate_hard_fail(ctx.cuts, ctx.channel)
            if remaining:
                yield f"WARN|[QualityAgent] {len(remaining)}개 HARD FAIL 잔존 (수동 확인 권장)\n"
            else:
                yield "[QualityAgent] HARD FAIL 전부 해결\n"

        if region_warns:
            yield f"WARN|[QualityAgent] {len(region_warns)}개 지역 스타일 경고\n"

        # 스크립트 동기화
        ctx.scripts = [c.get("script", "") for c in ctx.cuts]

        yield f"[QualityAgent] 검증 완료. {len(ctx.cuts)}컷\n"
