---
name: verify-pipeline
description: Verify the video generation pipeline code for correctness
disable-model-invocation: true
context: fork
---

Verify the AskAnything video pipeline end-to-end for code correctness.

Checklist:
1. **Cut validation**: Check `modules/gpt/cutter.py` enforces 6-10 cuts with retry
2. **Image pipeline**: Verify `modules/image/dalle.py` uses correct DALL-E 3 size and retry logic
3. **Video pipeline**: Verify `modules/video/kling.py` has proper timeout and fallback
4. **TTS pipeline**: Verify `modules/tts/elevenlabs.py` handles API errors gracefully
5. **Whisper**: Verify `modules/transcription/whisper.py` returns proper word timestamp format
6. **Remotion**: Verify `modules/video/remotion.py` generates correct props JSON and CLI command
7. **API Server**: Verify `api_server.py` SSE protocol (PROG|, DONE|, ERROR|) is consistent
8. **Frontend**: Verify `frontend/src/app/page.tsx` SSE parsing matches backend protocol
9. **Path consistency**: Verify output paths match between Remotion output and API static serving

Report format:
- PASS / FAIL / WARN per item
- For each FAIL: exact file:line and what needs to change
- Summary: pipeline ready or blocked
