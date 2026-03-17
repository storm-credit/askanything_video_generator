---
name: perf-profile
description: Analyze pipeline performance bottlenecks and API response times
context: fork
---

# Performance Profile — AskAnything

Analyze the video generation pipeline for performance bottlenecks.

## Pipeline Timing Model (per video, 8 cuts)

| Stage | Expected | Bottleneck Risk |
|-------|----------|-----------------|
| LLM Planning | 3-8s | Low (single call) |
| Fact-check (Tavily) | 2-5s | Low (cached after 1st) |
| Image Generation x8 | 15-40s | MEDIUM (parallel, but API limited) |
| Video Generation x8 | 60-180s | HIGH (sequential polling, 1-3min each) |
| TTS x8 | 5-15s | Low (parallel threads) |
| Whisper x8 | 5-15s | Low (parallel threads) |
| LUFS Normalization | 2-5s | Low (local ffmpeg) |
| Remotion Render | 30-90s | MEDIUM (CPU-bound) |
| **Total** | **~2-6 min** | |

## Check Points

### 1. Parallelism (`api_server.py`)
- `_cut_executor` max_workers = 4: is this optimal for the machine?
- Image generation: limited by `image_semaphore(2)` — check if API supports higher
- Video + TTS threads: spawned per-cut inside executor — verify no thread explosion
- Total concurrent threads: 4 workers x 3 threads = up to 12

### 2. API Timeouts
- [ ] `modules/gpt/cutter.py`: OpenAI/Gemini/Claude timeout=120s
- [ ] `modules/image/imagen.py`: HttpOptions timeout=120_000ms
- [ ] `modules/image/dalle.py`: OpenAI client timeout=120s
- [ ] `modules/video/veo.py`: polling MAX_WAIT=300s (5min)
- [ ] `modules/video/kling.py`: polling max_polls=90 x 5s = 450s (7.5min)
- [ ] `modules/video/engines.py`: Sora polling SORA_MAX_POLLS=60

### 3. Caching Effectiveness
- Image cache: `assets/.cache/images/` — SHA256 hash, 7-day expiry
- Fact-check cache: in-memory dict, 1-hour TTL
- No video caching (each generation is unique)

### 4. I/O Patterns
- Atomic writes: all file saves use tempfile + os.replace
- Image resize: PIL LANCZOS — most expensive per-image operation
- Audio: LUFS normalization via ffmpeg subprocess

### 5. Remotion Render
- Single-threaded by default (Remotion CLI)
- Consider: `--concurrency` flag for multi-core rendering
- Props JSON serialization: verify no oversized data

## When to Run
- After changing parallelism settings (executor workers, semaphores)
- After adding new pipeline stages
- When users report slow generation times
- Before scaling to multiple concurrent users
