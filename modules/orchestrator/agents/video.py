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

        # 히어로 컷 판별:
        # - hero_tier_indices: 서사/연출상 중요한 컷 3~5개
        # - hero_indices: 실제 생성형 비디오로 변환할 컷 1~2개
        # 포맷별 히어로 감정 태그 정의 (description 필드의 실제 태그 기준)
        # 유효 태그: SHOCK, WONDER, TENSION, REVEAL, URGENCY, DISBELIEF, IDENTITY, CALM
        _FORMAT_HERO_EMOTIONS: dict[str, set[str]] = {
            "WHO_WINS": {"SHOCK", "REVEAL", "DISBELIEF", "IDENTITY"},
            "IF": {"SHOCK", "REVEAL", "URGENCY", "DISBELIEF"},
            "EMOTIONAL_SCI": {"WONDER", "REVEAL", "CALM"},
            "FACT": {"SHOCK", "REVEAL", "DISBELIEF"},
            "COUNTDOWN": {"SHOCK", "REVEAL", "URGENCY", "IDENTITY"},
            "SCALE": {"WONDER", "SHOCK", "REVEAL"},
            "PARADOX": {"DISBELIEF", "REVEAL", "SHOCK"},
            "MYSTERY": {"TENSION", "REVEAL", "DISBELIEF"},
        }
        fmt = (ctx.format_type or "FACT").upper()
        hero_emotions = _FORMAT_HERO_EMOTIONS.get(fmt, {"SHOCK", "REVEAL"})
        hero_mode = ctx.video_model == "hero-only"
        high_motion_formats = {"WHO_WINS", "IF", "COUNTDOWN", "SCALE", "MYSTERY", "PARADOX"}

        def _extract_tags(text: str) -> set[str]:
            tags = set()
            for tag in ("SHOCK", "WONDER", "TENSION", "REVEAL", "URGENCY", "DISBELIEF", "IDENTITY", "CALM", "LOOP"):
                if f"[{tag}]" in (text or ""):
                    tags.add(tag)
            return tags

        def _score_video_worthiness(i: int, cut: dict) -> int:
            script = str(cut.get("script", ""))
            prompt = str(cut.get("prompt", ""))
            desc = str(cut.get("description", cut.get("text", "")))
            tags = _extract_tags(desc)
            combined = f"{script} {prompt} {desc}".lower()

            score = 0
            strong_tags = {"SHOCK", "REVEAL", "DISBELIEF", "URGENCY"}
            medium_tags = {"WONDER", "TENSION", "IDENTITY"}
            soft_tags = {"CALM", "LOOP"}

            score += 4 * len(tags & strong_tags)
            score += 2 * len(tags & medium_tags)
            score += 1 * len(tags & soft_tags)

            motion_keywords = (
                "vs", "versus", "split", "before", "after", "transform", "collision",
                "giant", "massive", "tiny", "scale", "silhouette", "reveal", "door",
                "rank", "#1", "top 1", "spotlight", "impact", "chase", "attack",
            )
            score += sum(1 for kw in motion_keywords if kw in combined)

            if fmt == "WHO_WINS" and any(kw in combined for kw in ("vs", "versus", "face", "split")):
                score += 3
            elif fmt == "IF" and any(kw in combined for kw in ("before", "after", "transform", "change")):
                score += 3
            elif fmt == "COUNTDOWN":
                score += max(0, i - max(0, len(ctx.cuts) - 4))
            elif fmt == "SCALE" and any(kw in combined for kw in ("giant", "massive", "tiny", "scale")):
                score += 3
            elif fmt == "MYSTERY" and any(kw in combined for kw in ("silhouette", "unknown", "fog", "door", "shadow")):
                score += 3
            elif fmt == "PARADOX" and any(kw in combined for kw in ("twist", "reversal", "opposite", "wrong")):
                score += 3
            elif fmt == "EMOTIONAL_SCI" and any(kw in combined for kw in ("heartbeat", "breath", "tear", "sleep", "brain", "body")):
                score += 2

            return score

        def _select_hero_tiers(
            scored_all: list[tuple[int, int]],
            video_candidates: list[tuple[int, int]],
        ) -> tuple[set[int], set[int]]:
            """중요 컷과 실제 영상화 컷을 분리한다."""
            if not scored_all:
                return set(), set()

            ranked = sorted(scored_all, key=lambda item: (-item[0], item[1]))
            tier_limit = min(5, max(3, len(ctx.cuts) // 2))
            hero_tier_indices = {idx for score, idx in ranked[:tier_limit] if score >= 3}

            video_ranked = sorted(video_candidates, key=lambda item: (-item[0], item[1]))
            max_video_cuts = 2 if fmt in high_motion_formats else 1
            video_indices = {
                idx for score, idx in video_ranked[:max_video_cuts]
                if score >= 6
            }

            # 강한 후보가 하나도 없으면 비용을 쓰지 않는다.
            return hero_tier_indices, video_indices

        def _mark_hero_metadata(hero_tier_indices: set[int], video_indices: set[int], scores: dict[int, int]) -> None:
            for i, cut in enumerate(ctx.cuts):
                if i in video_indices:
                    cut["hero_tier"] = "video"
                elif i in hero_tier_indices:
                    cut["hero_tier"] = "important"
                else:
                    cut["hero_tier"] = "normal"
                cut["video_selected"] = i in video_indices
                if i in scores:
                    cut["video_score"] = scores[i]

        if hero_mode:
            scored_all: list[tuple[int, int]] = []
            video_candidates: list[tuple[int, int]] = []
            for i, cut in enumerate(ctx.cuts):
                desc = str(cut.get("description", cut.get("text", "")))
                tags = _extract_tags(desc)
                score = _score_video_worthiness(i, cut)
                scored_all.append((score, i))
                if tags & hero_emotions and score >= 5:
                    video_candidates.append((score, i))

            if scored_all:
                scores = {idx: score for score, idx in scored_all}
                hero_tier_indices, hero_indices = _select_hero_tiers(scored_all, video_candidates)
                _mark_hero_metadata(hero_tier_indices, hero_indices, scores)
                tier_label = ",".join(str(i + 1) for i in sorted(hero_tier_indices)) or "-"
                video_label = ",".join(str(i + 1) for i in sorted(hero_indices)) or "-"
                skip_count = len(ctx.cuts) - len(hero_indices)
                yield (
                    f"[VideoAgent] 히어로 모드 ({fmt}): 중요 컷 {len(hero_tier_indices)}개 "
                    f"[{tier_label}], 실제 영상화 {len(hero_indices)}개 [{video_label}] "
                    f"({skip_count}컷 Ken Burns)\n"
                )
            else:
                hero_tier_indices = set()
                hero_indices = set()
                _mark_hero_metadata(hero_tier_indices, hero_indices, {})
                yield f"[VideoAgent] 히어로 모드 ({fmt}): 영상 가치 높은 컷 없음 — 전 컷 Ken Burns\n"
        else:
            hero_tier_indices = set(range(len(ctx.cuts)))
            hero_indices = set(range(len(ctx.cuts)))
            _mark_hero_metadata(hero_tier_indices, hero_indices, {})
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
                    veo_model=None if ctx.video_model == "hero-only" else ctx.video_model,
                    gemini_api_keys=ctx.gemini_keys_override,
                    format_type=ctx.format_type,
                    camera_style=ctx.camera_style,
                    use_hero_profile=ctx.video_model == "hero-only",
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
