"""MainOrchestrator — 에이전트 파이프라인 지휘자.

기존 api_server.py의 sse_generator() 700줄을 에이전트 단위로 분리.
동일한 SSE 프로토콜 (PROG|, WARN|, ERROR|, DONE|, UPLOAD_DONE|) 유지.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from typing import AsyncGenerator

from modules.orchestrator.base import AgentContext, ModelRouter
from modules.orchestrator.tracker import TokenTracker
from modules.orchestrator.agents.script import ScriptAgent
from modules.orchestrator.agents.quality import QualityAgent
from modules.orchestrator.agents.visual import VisualDirectorAgent
from modules.orchestrator.agents.polish import PolishAgent
from modules.orchestrator.agents.image import ImageAgent
from modules.orchestrator.agents.tts import TTSAgent
from modules.orchestrator.agents.video import VideoAgent
from modules.orchestrator.agents.render import RenderAgent
from modules.orchestrator.agents.upload import UploadAgent


class MainOrchestrator:
    """에이전트 파이프라인 오케스트라.

    Stage 1: Script (순차) → ScriptAgent
    Stage 2: Assets (병렬) → ImageAgent + TTSAgent
    Stage 3: Render (순차) → RenderAgent
    Stage 4: Upload (순차) → UploadAgent
    """

    def __init__(self, model_overrides: dict[str, str] | None = None):
        self._router = ModelRouter(overrides=model_overrides)

    async def run(self, ctx: AgentContext) -> AsyncGenerator[str, None]:
        tracker = TokenTracker(ctx)
        cost_recorded = False

        def _record_cost_once(success: bool) -> dict | None:
            nonlocal cost_recorded
            if cost_recorded:
                return None
            cost_recorded = True
            try:
                from modules.utils.cost_tracker import record_generation_cost

                return record_generation_cost(
                    channel=ctx.channel or "unknown",
                    success=success,
                    llm_usd=ctx.total_cost(),
                    image_count=ctx.image_count,
                    video_count=ctx.video_count,
                    video_model=ctx.video_model,
                    tts_chars=ctx.tts_chars,
                    image_cache_hits=ctx.image_cache_hits,
                    qwen_tts_chars=ctx.tts_chars_by_engine.get("qwen3", 0),
                    tts_engine_counts=ctx.tts_engine_counts,
                )
            except Exception as exc:
                print(f"[Orchestrator] 비용 기록 실패: {exc}")
                return None

        # 에이전트 인스턴스 생성
        script_agent = ScriptAgent(self._router, tracker)
        quality_agent = QualityAgent(self._router, tracker)
        visual_agent = VisualDirectorAgent(self._router, tracker)
        polish_agent = PolishAgent(self._router, tracker)
        image_agent = ImageAgent(self._router, tracker)
        tts_agent = TTSAgent(self._router, tracker)
        video_agent_inst = VideoAgent(self._router, tracker)
        render_agent = RenderAgent(self._router, tracker)
        upload_agent = UploadAgent(self._router, tracker)

        yield f"GEN_ID|{ctx.request_id}\n"

        # ── 사전 검증 ──
        pre_warnings = self._pre_validate(ctx)
        for w in pre_warnings:
            yield w

        yield "PROG|10\n"

        # ── YouTube URL 자동 감지 ──
        ctx.topic, ctx.reference_url = self._resolve_youtube_topic(
            ctx.topic, ctx.reference_url)

        # ── Stage 1: Script Pipeline (순차) ──
        try:
            async for msg in script_agent.execute(ctx):
                yield msg
        except Exception as exc:
            _record_cost_once(False)
            yield f"ERROR|[ScriptAgent] {self._safe_error(exc)}\n"
            return

        yield "PROG|30\n"

        # ── 콘텐츠 유형 자동 라우팅 ──
        from modules.orchestrator.content_router import classify_content, get_visual_recommendation
        content_type = classify_content(ctx.topic, ctx.cuts)
        rec = get_visual_recommendation(content_type)
        if content_type != "imagen":
            yield f"[Orchestrator] 콘텐츠 분석: {rec['description']}\n"
            # 비디오 엔진 자동 설정 (사용자가 명시적으로 지정하지 않은 경우)
            if ctx.video_engine == "none" and rec["video_engine"] != "none":
                ctx.video_engine = rec["video_engine"]

        # Review 모드: 여기서 중단
        if ctx.workflow_mode == "review":
            yield "REVIEW_READY|\n"
            yield "PROG|100\n"
            yield f"DONE|{ctx.topic_folder}\n"
            return

        if ctx.is_cancelled():
            yield "WARN|[취소됨] 사용자에 의해 생성이 취소되었습니다.\n"
            _record_cost_once(False)
            return

        # Phase 2: 검증/비주얼/폴리시를 독립 에이전트로 실행 (각자 다른 모델 사용)
        # 예산 기반 최적화: 토큰 초과 시 비핵심 에이전트 스킵
        budget_exceeded = tracker.is_request_over_budget()
        if budget_exceeded:
            yield f"WARN|[Orchestrator] 토큰 예산 초과 — 비핵심 검증 스킵\n"

        if not budget_exceeded:
            try:
                async for msg in quality_agent.execute(ctx):
                    yield msg
            except Exception as exc:
                yield f"WARN|[QualityAgent] {self._safe_error(exc)} — 스킵\n"
        else:
            yield "[Orchestrator] QualityAgent 스킵 (예산 초과)\n"

        yield "PROG|45\n"

        if not budget_exceeded:
            try:
                async for msg in visual_agent.execute(ctx):
                    yield msg
            except Exception as exc:
                yield f"WARN|[VisualDirectorAgent] {self._safe_error(exc)} — 스킵\n"
        else:
            yield "[Orchestrator] VisualDirectorAgent 스킵 (예산 초과)\n"

        yield "PROG|55\n"

        # PolishAgent는 항상 실행 (필수 — 금지 표현 필터링)
        try:
            async for msg in polish_agent.execute(ctx):
                yield msg
        except Exception as exc:
            yield f"WARN|[PolishAgent] {self._safe_error(exc)} — 스킵\n"

        try:
            from modules.gpt.cutter import _validate_hard_fail, _validate_region_style

            topic_title = ctx.topic.split("\n\n[원본 영상 내용]")[0].strip()
            for cut in ctx.cuts:
                cut.setdefault("format_type", ctx.format_type or "")
                cut.setdefault("topic", topic_title)
                cut.setdefault("topic_title", topic_title)
            final_hard_fails = _validate_hard_fail(ctx.cuts, ctx.channel)
            final_region_warns = _validate_region_style(ctx.cuts, ctx.channel)
            if final_hard_fails:
                yield f"ERROR|[QualityGate] 최종 HARD FAIL {len(final_hard_fails)}개 — 렌더 중단\n"
                for failure in final_hard_fails[:8]:
                    yield f"ERROR|  - {failure}\n"
                _record_cost_once(False)
                return
            if final_region_warns:
                yield f"WARN|[QualityGate] 최종 지역 스타일 경고 {len(final_region_warns)}개\n"
        except Exception as exc:
            yield f"WARN|[QualityGate] 최종 검증 실패(무시): {self._safe_error(exc)}\n"

        yield "PROG|60\n"

        # ── Stage 2: Asset Production (병렬) ──
        if ctx.is_cancelled():
            yield "WARN|[취소됨] 사용자에 의해 생성이 취소되었습니다.\n"
            _record_cost_once(False)
            return

        yield "[Orchestrator] 이미지 + TTS 병렬 생성 시작...\n"

        async def _collect_agent_msgs(agent) -> list[str]:
            msgs = []
            async for msg in agent.execute(ctx):
                msgs.append(msg)
            return msgs

        img_task = asyncio.create_task(_collect_agent_msgs(image_agent))
        tts_task = asyncio.create_task(_collect_agent_msgs(tts_agent))

        for task in asyncio.as_completed([img_task, tts_task]):
            try:
                msgs = await task
                for msg in msgs:
                    yield msg
            except Exception as exc:
                _record_cost_once(False)
                yield f"ERROR|[Asset] {self._safe_error(exc)}\n"
                return

        # 에셋 검증 — 실패한 컷 제거 후 나머지로 계속 진행 (웹 경로와 동일)
        failed_visual = [i for i, p in enumerate(ctx.visual_paths) if p is None]
        failed_audio = [i for i, p in enumerate(ctx.audio_paths) if p is None]
        failed_indices = set(failed_visual) | set(failed_audio)

        if failed_indices:
            details = []
            if failed_visual:
                details.append(f"이미지 실패: 컷 {[i+1 for i in failed_visual]}")
            if failed_audio:
                details.append(f"오디오 실패: 컷 {[i+1 for i in failed_audio]}")
            yield f"WARN|[소스 일부 실패] {', '.join(details)} — 나머지 컷으로 계속 진행\n"

            # 실패 컷 역순 제거 (인덱스 안정성)
            for i in sorted(failed_indices, reverse=True):
                ctx.cuts.pop(i)
                ctx.visual_paths.pop(i)
                ctx.audio_paths.pop(i)
                if hasattr(ctx, 'word_timestamps') and ctx.word_timestamps and i < len(ctx.word_timestamps):
                    ctx.word_timestamps.pop(i)

            if not ctx.cuts:
                yield f"ERROR|[소스 생성 오류] 전체 컷 실패 — 렌더링 불가\n"
                _record_cost_once(False)
                return
            ctx.scripts = [c.get("script", "") for c in ctx.cuts]

            post_asset_fails = self._validate_post_asset_cuts(ctx)
            if post_asset_fails:
                yield f"ERROR|[AssetGate] 실패 컷 제거 후 포맷 구조 붕괴 {len(post_asset_fails)}개 — 렌더 중단\n"
                for failure in post_asset_fails[:8]:
                    yield f"ERROR|  - {failure}\n"
                _record_cost_once(False)
                return

        yield "PROG|75\n"

        # ── Stage 2.5: Video Conversion (이미지→영상) 또는 Blender 3D ──
        if ctx.video_engine == "blender":
            # Blender 이미지 → Veo3 파이프라인 (향후)
            # 현재: BlenderAgent로 3D 렌더
            from modules.orchestrator.agents.blender import BlenderAgent
            blender_inst = BlenderAgent(self._router, tracker)
            try:
                async for msg in blender_inst.execute(ctx):
                    yield msg
            except Exception as exc:
                yield f"WARN|[BlenderAgent] {self._safe_error(exc)}\n"
        elif ctx.video_engine != "none":
            try:
                async for msg in video_agent_inst.execute(ctx):
                    yield msg
            except Exception as exc:
                yield f"WARN|[VideoAgent] {self._safe_error(exc)} — Ken Burns 대체\n"

        yield "PROG|85\n"

        if ctx.is_cancelled():
            yield "WARN|[취소됨] 사용자에 의해 생성이 취소되었습니다.\n"
            _record_cost_once(False)
            return

        # ── Stage 3: Render ──
        try:
            async for msg in render_agent.execute(ctx):
                yield msg
        except Exception as exc:
            _record_cost_once(False)
            yield f"ERROR|[RenderAgent] {self._safe_error(exc)}\n"
            return

        if not ctx.video_paths:
            _record_cost_once(False)
            yield "ERROR|[RenderAgent] 렌더링 결과가 없습니다.\n"
            return

        yield "PROG|95\n"

        # Downloads 폴더 자동 복사
        self._save_to_downloads(ctx)

        # 프론트엔드 경로
        primary = list(ctx.video_paths.keys())[0]
        video_path = ctx.video_paths[primary]
        final_filename = os.path.basename(video_path)
        relative_video_path = f"/assets/{ctx.topic_folder}/video/{final_filename}"

        yield f"[완료] 렌더링 대성공! {final_filename}\n"

        # ── Stage 4: Upload (조건부) ──
        if ctx.publish_mode != "local":
            try:
                async for msg in upload_agent.execute(ctx):
                    yield msg
            except Exception as exc:
                yield f"WARN|[UploadAgent] {self._safe_error(exc)}\n"

        yield "PROG|100\n"

        # 토큰 요약
        summary = tracker.summary()
        if summary["calls"] > 0:
            yield (f"[Orchestrator] 토큰: {summary['total_tokens']:,} | "
                   f"비용: ${summary['total_cost_usd']}\n")

        cost_entry = _record_cost_once(True)
        if cost_entry:
            yield (
                f"[Orchestrator] 비용집계: LLM ${cost_entry['llm_usd']:.4f} | "
                f"이미지 {ctx.image_count}장(cache {ctx.image_cache_hits}) | "
                f"비디오 {ctx.video_count}컷 | TTS {ctx.tts_engine_counts}\n"
            )

        # 썸네일 경로
        thumb_relative = ""
        if ctx.thumbnail_path and os.path.exists(ctx.thumbnail_path):
            thumb_relative = f"/assets/{ctx.topic_folder}/video/thumbnail.jpg"

        yield f"DONE|{relative_video_path}|{thumb_relative}\n"

    # ── Helper Methods ──

    def _pre_validate(self, ctx: AgentContext) -> list[str]:
        """사전 검증: API 키 가용성 경고."""
        warnings = []
        from modules.utils.keys import count_google_keys, count_available_keys
        total = count_google_keys(extra_keys=ctx.gemini_keys_override)
        avail = count_available_keys(extra_keys=ctx.gemini_keys_override)
        if total > 0 and avail < total:
            blocked = total - avail
            if avail == 0:
                warnings.append(f"WARN|[Google 키 경고] 모든 {total}개 키가 429 차단됨.\n")
            else:
                warnings.append(f"WARN|[Google 키 상태] {avail}/{total}개 사용 가능 ({blocked}개 차단 중)\n")
        return warnings

    @staticmethod
    def _resolve_youtube_topic(topic: str, ref_url: str | None) -> tuple[str, str | None]:
        """YouTube URL 자동 감지 + topic 교체."""
        try:
            from modules.utils.youtube_extractor import extract_youtube_reference
            import re as _re
            yt_pattern = _re.compile(r'(https?://(?:www\.)?(?:youtube\.com|youtu\.be)/\S+)')
            match = yt_pattern.search(topic)
            if match and not ref_url:
                ref_url = match.group(1)
            if ref_url:
                result = extract_youtube_reference(ref_url)
                if result and result.get("title"):
                    yt_title = result["title"]
                    transcript = result.get("transcript", "")
                    if transcript:
                        topic = f"{yt_title}\n\n[원본 영상 내용]\n{transcript}"
                    else:
                        topic = yt_title
        except Exception:
            pass
        return topic, ref_url

    @staticmethod
    def _save_to_downloads(ctx: AgentContext):
        """Downloads 폴더로 자동 복사."""
        if not ctx.video_paths:
            return
        dl_base = os.environ.get("DOWNLOAD_DIR",
                                 os.path.join(os.path.expanduser("~"), "Downloads"))
        if not os.path.isdir(dl_base):
            return
        primary = list(ctx.video_paths.keys())[0]
        video_path = ctx.video_paths[primary]
        channel = ctx.channel or "default"
        dl_dir = os.path.join(dl_base, ctx.topic_folder)
        os.makedirs(dl_dir, exist_ok=True)
        try:
            dl_path = os.path.join(dl_dir, f"{channel}.mp4")
            shutil.copy2(os.path.abspath(video_path), dl_path)
        except Exception as exc:
            print(f"[Orchestrator] Downloads 복사 실패: {exc}")

    @staticmethod
    def _validate_post_asset_cuts(ctx: AgentContext) -> list[str]:
        """Validate that removing failed asset cuts did not break format structure."""
        failures: list[str] = []
        topic_title = ctx.topic.split("\n\n[원본 영상 내용]")[0].strip()
        for cut in ctx.cuts:
            cut.setdefault("format_type", ctx.format_type or "")
            cut.setdefault("topic", topic_title)
            cut.setdefault("topic_title", topic_title)

        try:
            from modules.gpt.cutter import _validate_hard_fail
            failures.extend(_validate_hard_fail(ctx.cuts, ctx.channel))
        except Exception as exc:
            failures.append(f"POST_ASSET_HARD_FAIL_CHECK_ERROR: {exc}")

        fmt = (ctx.format_type or next(
            (str(c.get("format_type", "")).upper() for c in ctx.cuts if c.get("format_type")),
            "",
        )).upper()
        try:
            from modules.gpt.prompts.formats import get_format_cut_override
            from modules.utils.channel_config import get_channel_preset

            preset = get_channel_preset(ctx.channel) if ctx.channel else None
            channel_min = (preset or {}).get("min_cuts", 8)
            channel_max = (preset or {}).get("max_cuts", 10)
            min_cuts, max_cuts = get_format_cut_override(fmt, channel_min, channel_max)
            format_cuts = (preset or {}).get("format_cuts", {}).get(fmt, {}) if fmt else {}
            min_cuts = format_cuts.get("min") or min_cuts
            max_cuts = format_cuts.get("max") or max_cuts
            if len(ctx.cuts) < min_cuts or len(ctx.cuts) > max_cuts:
                failures.append(
                    f"FORMAT_CUT_COUNT_AFTER_ASSET: {fmt or 'DEFAULT'} {len(ctx.cuts)}컷 "
                    f"(필수 {min_cuts}~{max_cuts}컷)"
                )
        except Exception as exc:
            failures.append(f"POST_ASSET_CUT_COUNT_CHECK_ERROR: {exc}")

        return failures

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        """API 키 마스킹된 에러 문자열."""
        err_str = str(exc)[:200]
        return re.sub(r"(AIza|sk-|key=|token=|Bearer )[A-Za-z0-9_\-]{4,}",
                      r"\1***", err_str)
