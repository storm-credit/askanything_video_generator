---
name: backend-patterns
description: FastAPI backend patterns, SSE streaming, and caching conventions
---

# Backend Patterns — AskAnything

## FastAPI Conventions

### SSE Streaming
All long-running endpoints use Server-Sent Events:
```python
from starlette.responses import StreamingResponse

async def sse_generator():
    yield f"data: {json.dumps({'type': 'progress', 'message': '...'})}\n\n"
    # ... pipeline steps ...
    yield f"data: {json.dumps({'type': 'complete', 'result': '...'})}\n\n"

return StreamingResponse(sse_generator(), media_type="text/event-stream")
```

### Request Validation
- Use Pydantic models with field validators
- Camera style: `Literal["auto", "dynamic", "gentle", "static"]`, default `"auto"`
- Language: validate against 18-language list
- Platform: `List[str]` with empty list default

### Concurrency Control
```python
_generate_semaphore = asyncio.Semaphore(1)
async with _generate_semaphore:
    os.environ["KEY"] = value  # Safe inside semaphore
    result = await pipeline()
```
Only set `os.environ` inside the semaphore to prevent race conditions.

### Session Management
- Sessions stored in `dict` with UUID keys
- Session expiry: clean up old sessions periodically
- Always `copy.deepcopy()` when reading session data for render

### CORS
Explicit port list, never wildcard in production:
```python
origins = ["http://localhost:3000", "http://localhost:3001"]
```

## Caching (`modules/utils/cache.py`)
- MD5 hash of prompt → cached image path
- 7-day expiry (`CACHE_MAX_AGE = 7 * 86400`)
- Check cache before any image generation call
- Atomic write for cache files

## Security
- Path traversal: `os.path.abspath(os.path.realpath(path))`
- SQL injection: whitelist allowed column names in batch.py
- No `.env` or credentials in responses
- Mask API keys in health endpoint (show last 4 chars only)

## File Structure
```
api_server.py          # Routes, models, SSE generators
modules/
  gpt/                 # LLM planning (cutter.py, search.py)
  image/               # Image gen (dalle.py, imagen.py)
  video/               # Video gen (veo.py, kling.py, engines.py, remotion.py)
  tts/                 # TTS (elevenlabs.py)
  transcription/       # STT (whisper.py)
  utils/               # Shared (keys.py, cache.py, safety.py, constants.py, audio.py, batch.py)
```
