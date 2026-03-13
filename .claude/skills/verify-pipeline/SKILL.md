---
name: verify-pipeline
description: Verify the full video generation pipeline code for correctness (multi-engine)
context: fork
---

Verify the AskAnything video pipeline end-to-end for code correctness.
This project uses multi-engine support (Gemini/GPT/Claude LLM, Imagen/DALL-E image, Veo/Kling video).

Checklist:
1. **Cut validation**: Check `modules/gpt/cutter.py` enforces 6-10 cuts with retry
2. **Image pipeline (DALL-E)**: Verify `modules/image/dalle.py` uses correct size (1024x1792) and retry
3. **Image pipeline (Imagen 4)**: Verify `modules/image/imagen.py` uses `imagen-4.0-generate-001`, safety filter, 429 auto-retry with key rotation
4. **Video engine router**: Verify `modules/video/engines.py` routes to correct engine (veo3/kling/sora2/hailuo/wan/none), `check_engine_available()` works
5. **Video pipeline (Veo 3)**: Verify `modules/video/veo.py` has polling loop, 429 auto-retry with `mark_key_exhausted`, `MAX_KEY_RETRIES=3`
6. **Video pipeline (Kling)**: Verify `modules/video/kling.py` has JWT auth, polling with timeout
7. **TTS pipeline**: Verify `modules/tts/elevenlabs.py` handles errors gracefully, `check_quota()` returns remaining chars
8. **Whisper**: Verify `modules/transcription/whisper.py` returns proper word timestamp format
9. **Remotion**: Verify `modules/video/remotion.py` generates correct props JSON and CLI command, dynamic filename
10. **Key rotation**: Verify `modules/utils/keys.py` has 3-state management (active/warning/blocked), per-service blocking, `get_google_key(service=, exclude=)`
11. **API Server**: Verify `api_server.py` SSE protocol (PROG|, DONE|, ERROR|, WARN|) is consistent, `active_video_engine` scoping correct
12. **Frontend**: Verify `frontend/src/app/page.tsx` SSE parsing matches all 4 protocols, key usage stats display
13. **Path consistency**: Verify output paths match between Remotion output and API static serving

Report format:
- PASS / FAIL / WARN per item
- For each FAIL: exact file:line and what needs to change
- Summary: pipeline ready or blocked
