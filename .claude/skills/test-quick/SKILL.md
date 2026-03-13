---
name: test-quick
description: Quick smoke test of the video generation pipeline (no actual generation)
context: fork
---

Run a quick smoke test to verify the pipeline code loads and API connections work.

Steps:
1. **Import checks** - verify all modules load without error:
   ```
   python -c "from modules.gpt.cutter import plan_cuts; print('cutter OK')"
   python -c "from modules.image.dalle import generate_image; print('dalle OK')"
   python -c "from modules.image.imagen import generate_image_imagen; print('imagen OK')"
   python -c "from modules.video.veo import generate_video_veo; print('veo OK')"
   python -c "from modules.video.kling import generate_video_kling; print('kling OK')"
   python -c "from modules.video.engines import get_available_engines; print('engines OK')"
   python -c "from modules.tts.elevenlabs import generate_tts; print('tts OK')"
   python -c "from modules.transcription.whisper import transcribe_audio; print('whisper OK')"
   python -c "from modules.video.remotion import create_remotion_video; print('remotion OK')"
   python -c "from modules.utils.keys import get_google_key, get_key_usage_stats; print('keys OK')"
   python -c "import api_server; print('api_server OK')"
   ```

2. **Server health** - check backend responds:
   ```
   curl -s http://localhost:8000/api/health
   curl -s http://localhost:8000/api/key-usage
   ```

3. **Dry run** - test SSE endpoint with videoEngine=none (no actual image/video generation):
   ```
   curl -s -N -X POST http://localhost:8000/api/generate \
     -H "Content-Type: application/json" \
     -d '{"topic":"test","videoEngine":"none"}'
   ```
   Verify SSE protocol: PROG|, DONE| or ERROR| messages received.

4. **Report**: PASS/FAIL per check, with error details for any failures.

This test does NOT consume API quota (uses videoEngine=none for dry run).
