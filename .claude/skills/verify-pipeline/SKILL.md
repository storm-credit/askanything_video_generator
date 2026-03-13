---
name: verify-pipeline
description: Verify the full video generation pipeline code for correctness (multi-engine)
context: fork
---

Verify the AskAnything video pipeline end-to-end for code correctness.
This project uses multi-engine support (Gemini/GPT/Claude LLM, Imagen/DALL-E image, Veo/Kling video).

Checklist:
1. **Cut validation**: Check `modules/gpt/cutter.py` enforces 6-10 cuts with retry, supports `lang` parameter (ko/en)
2. **Image pipeline (DALL-E)**: Verify `modules/image/dalle.py` uses correct size (1024x1792) and retry
3. **Image pipeline (Imagen 4)**: Verify `modules/image/imagen.py` uses `imagen-4.0-generate-001`, safety filter, 429 auto-retry with key rotation
4. **Video engine router**: Verify `modules/video/engines.py` routes to correct engine (veo3/kling/sora2/none), `check_engine_available()` works
5. **Video pipeline (Veo 3)**: Verify `modules/video/veo.py` has polling loop, 429 auto-retry with `mark_key_exhausted`, `MAX_KEY_RETRIES=3`
6. **Video pipeline (Kling)**: Verify `modules/video/kling.py` has JWT auth, polling with timeout, no dead token refresh code
7. **TTS pipeline**: Verify `modules/tts/elevenlabs.py` handles errors gracefully, `check_quota()` returns remaining chars
8. **Whisper**: Verify `modules/transcription/whisper.py` accepts `language` parameter (ko/en), returns proper word timestamp format
9. **Remotion render**: Verify `modules/video/remotion.py` generates correct props JSON including `bgmPath`, `introImagePath`, `outroImagePath`, `title`, and CLI command
10. **Remotion composition**: Verify `remotion/src/Main.tsx` has TitleOverlay (2.5s on first cut), BGM Audio (volume 0.15, loop), 1s intro/outro
11. **Remotion Root**: Verify `remotion/src/Root.tsx` passes all props (cuts, introImagePath, outroImagePath, bgmPath, title)
12. **Key rotation**: Verify `modules/utils/keys.py` has 3-state management (active/warning/blocked), per-service blocking, returns None when all exhausted
13. **API Server**: Verify `api_server.py` SSE protocol (PROG|, DONE|, ERROR|, WARN|), thread lock on errors list, language parameter flow, differentiated timeouts (300s video, 60s TTS)
14. **Frontend**: Verify `frontend/src/app/page.tsx` SSE parsing matches all 4 protocols, language selector (ko/en), key usage stats display
15. **Brand assets**: Verify `brand/` folder has bgm.mp3, intro.png, outro.png and they are auto-copied to assets
16. **Path consistency**: Verify output paths match between Remotion output and API static serving

Report format:
- PASS / FAIL / WARN per item
- For each FAIL: exact file:line and what needs to change
- Summary: pipeline ready or blocked
