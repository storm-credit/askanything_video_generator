# AskAnything Video Generator - Project Rules

## Project Overview
AI-powered shorts video generator. Text topic → 30-60s vertical video (9:16).
Pipeline: Gemini/GPT planning → Imagen/DALL-E images → Veo3/Kling video → ElevenLabs TTS → Whisper timestamps → Remotion render.

## Tech Stack
- **Backend**: Python 3.10+ (FastAPI, Google Gemini, OpenAI, Tavily, ElevenLabs, Kling AI)
- **Frontend**: Next.js 16 (React 19, TypeScript, Tailwind CSS 4, Framer Motion)
- **Renderer**: Remotion 4 (React-based video composition, TypeScript)
- **Language**: Korean (UI/prompts), English (code/comments)

## Key Paths
- `api_server.py` - FastAPI main server (port 8003)
- `modules/` - Core pipeline (gpt/, image/, video/, tts/, transcription/, utils/)
- `frontend/` - Next.js web UI (port 3000)
- `remotion/` - React video renderer
- `assets/` - Generated outputs (gitignored)

## Commands
- **Backend**: `python api_server.py` (uvicorn on port 8003)
- **Frontend**: `npm --prefix frontend run dev`
- **Remotion install**: `npm --prefix remotion install`
- **Preflight check**: `python preflight_check.py`
- **Syntax check**: `python syntax_check.py`
- **Test pipeline**: `python test_pipeline.py`

## Required Environment Variables
```
GEMINI_API_KEY=       # Gemini planning, Imagen, Veo3 (primary)
OPENAI_API_KEY=       # GPT, DALL-E, Whisper
ELEVENLABS_API_KEY=   # TTS voice
TAVILY_API_KEY=       # Fact-check search (optional)
KLING_ACCESS_KEY=     # Cinematic video (optional)
KLING_SECRET_KEY=     # Cinematic video (optional)
```

## Code Style
- Python: snake_case, type hints preferred, Korean print messages for user-facing logs
- TypeScript/React: PascalCase components, camelCase variables
- No unnecessary comments or docstrings on obvious code
- Keep functions small and focused

## Pipeline Rules
- Cuts must be 6-10 per video (enforced in cutter.py with retry)
- Default engines: Gemini (LLM) + Imagen (image) + Veo3 (video)
- Imagen/DALL-E images: vertical 1024x1792, NO text in images
- Audio: ElevenLabs primary, LUFS normalized to -14 dB
- Veo3/Kling: async polling with timeout, fallback to static image
- Remotion: 30fps, 9:16 aspect ratio (no intro, outro only)

## Git
- Branch: feature branches off main
- Commit messages: Korean description OK, conventional style preferred
- Never commit .env or API keys
