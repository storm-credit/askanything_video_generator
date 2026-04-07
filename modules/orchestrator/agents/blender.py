"""BlenderAgent — 3D 영상 생성 (행성/크기 비교/구조 시각화).

blender/planet_comparison.py를 서브프로세스로 실행.
콘텐츠 라우터가 "blender_3d"로 분류한 토픽에 대해 자동 호출.
Blender가 설치된 환경에서만 동작.
"""

from __future__ import annotations

import os
import asyncio
import shutil
import subprocess
from typing import AsyncGenerator

from modules.orchestrator.base import BaseAgent, AgentContext


BLENDER_BIN = os.getenv("BLENDER_BIN", "blender")
BLENDER_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "blender"
)

# 사용 가능한 프리셋 목록
PRESETS = {
    "solar_system": {"name": "태양계 크기 비교", "script": "planet_comparison.py"},
    "giant_stars": {"name": "별 크기 비교", "script": "planet_comparison.py"},
}


class BlenderAgent(BaseAgent):
    """3D 렌더링 에이전트. LLM 호출 없음."""

    name = "BlenderAgent"

    async def execute(self, ctx: AgentContext) -> AsyncGenerator[str, None]:
        """콘텐츠 라우터에서 blender_3d로 분류된 경우 자동 호출.

        현재는 토픽에서 프리셋을 자동 매칭하여 렌더링.
        매칭 실패 시 pass-through (Imagen 폴백).
        """
        preset = self._match_preset(ctx.topic, ctx.cuts)
        if not preset:
            yield "[BlenderAgent] 매칭되는 3D 프리셋 없음 — Imagen으로 진행\n"
            return

        async for msg in self.render_comparison(preset):
            yield msg

    def _match_preset(self, topic: str, cuts: list[dict] | None = None) -> str | None:
        """토픽에서 적절한 Blender 프리셋 자동 매칭."""
        topic_lower = topic.lower()
        all_text = topic_lower
        if cuts:
            for c in cuts:
                all_text += " " + c.get("script", "").lower()

        # 별/항성 크기 비교
        star_keywords = ["별 크기", "star size", "항성", "베텔게우스", "betelgeuse",
                         "uy scuti", "시리우스", "sirius", "red giant", "적색거성"]
        if any(kw in all_text for kw in star_keywords):
            return "giant_stars"

        # 태양계/행성 크기 비교
        planet_keywords = ["태양계", "solar system", "행성 크기", "planet size",
                          "목성", "jupiter", "토성", "saturn", "해왕성", "neptune"]
        if any(kw in all_text for kw in planet_keywords):
            return "solar_system"

        return None

    async def render_comparison(self, preset: str = "solar_system",
                                output_dir: str | None = None,
                                ) -> AsyncGenerator[str, None]:
        """행성/별 크기 비교 영상 렌더링."""
        blender_path = shutil.which(BLENDER_BIN)
        if not blender_path:
            yield f"WARN|[BlenderAgent] Blender 미설치 — BLENDER_BIN 환경변수 확인\n"
            return

        preset_info = PRESETS.get(preset)
        if not preset_info:
            yield f"WARN|[BlenderAgent] 알 수 없는 프리셋: {preset}\n"
            return

        script_path = os.path.join(BLENDER_DIR, preset_info["script"])
        if not os.path.exists(script_path):
            yield f"WARN|[BlenderAgent] 스크립트 없음: {script_path}\n"
            return

        yield f"[BlenderAgent] {preset_info['name']} 렌더링 시작...\n"

        cmd = [blender_path, "--background", "--python", script_path, "--", preset]

        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    cmd, capture_output=True, text=True, timeout=300,
                    cwd=BLENDER_DIR,
                ),
            )

            if result.returncode == 0:
                default_output = os.path.join(BLENDER_DIR, "output", f"{preset}_comparison.mp4")
                if os.path.exists(default_output):
                    yield f"[BlenderAgent] 렌더링 완료: {default_output}\n"
                else:
                    yield f"WARN|[BlenderAgent] 렌더링 완료했으나 출력 파일 없음\n"
            else:
                stderr = result.stderr[:300] if result.stderr else "알 수 없는 오류"
                yield f"WARN|[BlenderAgent] 렌더링 실패: {stderr}\n"

        except subprocess.TimeoutExpired:
            yield "WARN|[BlenderAgent] 렌더링 타임아웃 (5분 초과)\n"
        except Exception as exc:
            yield f"WARN|[BlenderAgent] {exc}\n"
