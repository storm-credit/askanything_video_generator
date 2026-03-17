---
name: codebase-overview
description: Explain project architecture, folder structure, and where things live
---

# AskAnything Video Generator - Codebase Overview

## Pipeline Flow
```
Topic Input → LLM Planning → Image Generation → Video Generation → TTS → Whisper → Remotion Render → Output
```

## Backend (Python 3.10+, FastAPI)
- `api_server.py` — Main server (port 8003), SSE endpoints, request models
- `modules/gpt/cutter.py` — LLM cut planning (Gemini/OpenAI/Claude), 7-10 cuts
- `modules/gpt/search.py` — Tavily fact-check RAG context
- `modules/image/dalle.py` — DALL-E 3 image generation (1024x1792)
- `modules/image/imagen.py` — Google Imagen image generation
- `modules/video/veo.py` — Google Veo 3 video generation
- `modules/video/kling.py` — Kling AI video generation (JWT auth)
- `modules/video/engines.py` — Video engine router + dynamic fallback
- `modules/tts/elevenlabs.py` — ElevenLabs TTS (Eric voice default)
- `modules/transcription/whisper.py` — OpenAI Whisper word timestamps
- `modules/video/remotion.py` — Remotion CLI render wrapper

## Backend Utilities
- `modules/utils/keys.py` — Multi-key rotation (active/warning/blocked states)
- `modules/utils/batch.py` — SQLite batch job queue
- `modules/utils/cache.py` — Image prompt hash cache (MD5, 7-day expiry)
- `modules/utils/safety.py` — Unified safety fallback for image prompts
- `modules/utils/constants.py` — MASTER_STYLE, get_motion_style()
- `modules/utils/audio.py` — LUFS normalization (-14 dB target)

## Frontend (Next.js 16, React 19, TypeScript)
- `frontend/src/app/page.tsx` — Main page, SSE handling, 3-column control grid
- `frontend/src/components/SettingsModal.tsx` — API key management (2-tab)
- `frontend/src/components/types.ts` — KEY_CONFIGS, type definitions

## Renderer (Remotion 4, React)
- `remotion/src/Main.tsx` — Video composition, Ken Burns, FadeIn, DynamicBgmAudio
- `remotion/src/Captions.tsx` — Hormozi-style word captions, emotion colors
- `remotion/src/Root.tsx` — Remotion entry point, props parsing

## API Endpoints
- `POST /api/generate` — Full pipeline (SSE stream)
- `POST /api/prepare` — Preview: LLM + images only (SSE)
- `POST /api/render` — Render from prepared session (SSE)
- `GET /api/health` — Key status + masked keys
- `GET /api/key-usage` — Per-key usage stats
- `POST /api/batch/submit` — Batch job queue

## Conventions
- Camera style default: `auto` (emotion-based Ken Burns)
- All image prompts prefixed with `MASTER_STYLE` from constants.py
- Video prompts use `get_motion_style()` for emotion-based camera motion
- Atomic file writes for all downloads (tempfile + os.replace)
- API key rotation: 3-state (active → warning → blocked/24h)
- Session data uses `copy.deepcopy()` to prevent mutation
- `_generate_semaphore = 1` prevents concurrent env var conflicts
