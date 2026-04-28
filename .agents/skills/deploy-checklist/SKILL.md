---
name: deploy-checklist
description: Pre-deployment checklist combining preflight, pipeline verify, and security checks
context: fork
---

# Deploy Checklist — AskAnything

Run all critical checks before deploying or merging to main.

## Steps

1. **Environment** — Run `python preflight_check.py` and verify:
   - [ ] Python 3.10+, ffmpeg, ffprobe, npx installed
   - [ ] All required packages in requirements.txt installed
   - [ ] remotion/node_modules exists
   - [ ] At least one LLM key set (GEMINI or OPENAI)
   - [ ] ELEVENLABS_API_KEY set
   - [ ] assets/ directory exists

2. **Syntax** — Run `python syntax_check.py` or:
   ```bash
   python -m py_compile api_server.py
   python -m py_compile modules/gpt/cutter.py
   python -m py_compile modules/image/imagen.py
   python -m py_compile modules/image/dalle.py
   python -m py_compile modules/video/veo.py
   python -m py_compile modules/video/kling.py
   python -m py_compile modules/video/engines.py
   python -m py_compile modules/tts/elevenlabs.py
   python -m py_compile modules/transcription/whisper.py
   ```

3. **Pipeline Integrity** — Verify data flow:
   - [ ] Cuts: 7-10 enforced (cutter.py validation)
   - [ ] Images: 1024x1792 vertical, MASTER_STYLE prefix
   - [ ] Video: engine fallback chain works (veo3 → kling → sora2)
   - [ ] TTS: language parameter flows through
   - [ ] Whisper: word timestamps return [{word, start, end}]
   - [ ] Remotion: all props passed (cuts, cameraStyle, captionSize, captionY, bgmPath)
   - [ ] Brand assets: intro/outro auto-copied from brand/

4. **Security** — Quick scan:
   - [ ] No hardcoded API keys (grep for sk-, AIza)
   - [ ] .env in .gitignore
   - [ ] OAuth callbacks use html.escape()
   - [ ] Upload paths use is_relative_to()
   - [ ] requirements.txt has version ranges pinned

5. **Git** — Check branch state:
   - [ ] No uncommitted changes
   - [ ] Branch up to date with remote
   - [ ] All tests/checks pass

## Output
Report as: READY / BLOCKED (with reason)
