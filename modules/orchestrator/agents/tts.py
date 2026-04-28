"""TTSAgent — TTS 생성 + Whisper 타임스탬프 + 비디오 변환.

api_server.py의 process_cut() TTS/비디오 로직을 래핑.
LLM 호출 없음.
"""

from __future__ import annotations

import os
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncGenerator

from modules.orchestrator.base import BaseAgent, AgentContext


class TTSAgent(BaseAgent):
    name = "TTSAgent"

    async def execute(self, ctx: AgentContext) -> AsyncGenerator[str, None]:
        from modules.tts.elevenlabs import generate_tts, prepare_spoken_script
        from modules.transcription.whisper import (
            align_words_with_script,
            build_fallback_word_timestamps,
            generate_word_timestamps,
        )
        from modules.utils.audio import normalize_audio_lufs, probe_audio_duration
        from modules.utils.channel_config import get_channel_preset

        if not ctx.cuts:
            yield "WARN|[TTSAgent] 컷이 없습니다.\n"
            return

        ctx.audio_paths = [None] * len(ctx.cuts)
        ctx.word_timestamps = [None] * len(ctx.cuts)

        # 음성 설정 resolve
        voice_id = ctx.voice_id
        voice_settings = ctx.voice_settings
        if not voice_id and ctx.channel:
            preset = get_channel_preset(ctx.channel)
            if preset:
                voice_id = preset.get("voice_id")
                voice_settings = preset.get("voice_settings")

        yield f"[TTSAgent] {len(ctx.cuts)}컷 TTS + 타임스탬프 생성 시작...\n"

        def _process_tts(i: int, cut: dict) -> tuple[int, str | None, list | None]:
            if ctx.is_cancelled():
                return i, None, None

            audio_path = None
            timestamps = None
            spoken_script = prepare_spoken_script(cut.get("script", ""), ctx.language)
            cut["script"] = spoken_script

            # 감정 태그 추출
            emotion = None
            desc = cut.get("description", cut.get("text", ""))
            for tag in ["SHOCK", "WONDER", "TENSION", "REVEAL", "URGENCY", "DISBELIEF", "IDENTITY", "CALM", "LOOP"]:
                if f"[{tag}]" in desc:
                    emotion = tag
                    break

            # TTS 생성
            try:
                audio_path = generate_tts(
                    spoken_script, i, ctx.topic_folder,
                    ctx.elevenlabs_key,
                    language=ctx.language, speed=ctx.tts_speed,
                    voice_id=voice_id, voice_settings=voice_settings,
                    emotion=emotion, channel=ctx.channel, already_prepared=True)
            except Exception as exc:
                print(f"[TTSAgent] 컷 {i+1} TTS 실패: {exc}")
                return i, None, None

            # LUFS 정규화
            if audio_path:
                try:
                    audio_path = normalize_audio_lufs(audio_path)
                except Exception as exc:
                    print(f"[TTSAgent] 컷 {i+1} LUFS 정규화 경고: {exc}")

            # Whisper 타임스탬프
            if audio_path:
                try:
                    raw_ts = generate_word_timestamps(
                        audio_path, ctx.api_key_override,
                        language=ctx.language)
                    timestamps = align_words_with_script(raw_ts, spoken_script, lang=ctx.language)
                except Exception as exc:
                    print(f"[TTSAgent] 컷 {i+1} 타임스탬프 실패: {exc}")
            if audio_path and not timestamps:
                audio_duration = probe_audio_duration(audio_path)
                timestamps = build_fallback_word_timestamps(spoken_script, audio_duration)

            return i, audio_path, timestamps

        executor = ThreadPoolExecutor(max_workers=4)
        loop = asyncio.get_running_loop()
        tasks = [loop.run_in_executor(executor, _process_tts, i, cut)
                 for i, cut in enumerate(ctx.cuts)]

        for coro in asyncio.as_completed(tasks):
            i, aud_path, timestamps = await coro
            ctx.audio_paths[i] = aud_path
            ctx.word_timestamps[i] = timestamps
            if aud_path and i < len(ctx.cuts):
                ctx.tts_chars += len(ctx.cuts[i].get("script", ""))
            status = "OK" if aud_path else "FAILED"
            yield f"  -> 컷 {i+1} TTS {status}\n"

        executor.shutdown(wait=False)

        failed = [i+1 for i, p in enumerate(ctx.audio_paths) if p is None]
        if failed:
            yield f"WARN|[TTSAgent] TTS 실패: 컷 {failed}\n"
        else:
            yield f"[TTSAgent] 전체 {len(ctx.cuts)}컷 TTS 완료\n"
