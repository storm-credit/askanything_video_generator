---
name: cost-aware-llm-pipeline
description: Optimize LLM/API costs across the video generation pipeline
---

# Cost-Aware LLM Pipeline Review

Review and optimize API cost usage across the AskAnything pipeline.

## Cost Model (per video)
| Service | Call | Est. Cost |
|---------|------|-----------|
| Gemini 2.0 Flash | Cut planning (~2K tokens) | ~$0.001 |
| Gemini 2.5 Pro | Cut planning fallback | ~$0.02 |
| GPT-4o | Cut planning fallback | ~$0.03 |
| Tavily Search | 1 query per video | ~$0.01 |
| Imagen 3 | 7-10 images | ~$0.28-0.40 |
| DALL-E 3 | 7-10 images (fallback) | ~$0.56-0.80 |
| Veo 3 | 7-10 clips | ~$0.35-0.50 |
| Kling AI | 7-10 clips (fallback) | ~$1.40-2.00 |
| ElevenLabs | ~200 words TTS | ~$0.03 |
| Whisper | ~45s audio | ~$0.005 |

## Optimization Checklist

### 1. Image Prompt Caching (`modules/utils/cache.py`)
- [ ] Cache hit rate logged? Check MD5 hash collisions
- [ ] 7-day expiry appropriate? Adjust `CACHE_MAX_AGE` if needed
- [ ] Cache used in both `imagen.py` and `dalle.py`?

### 2. LLM Token Efficiency (`modules/gpt/cutter.py`)
- [ ] System prompt minimal (no redundant instructions)
- [ ] Golden examples trimmed (should be 3, not 10)
- [ ] Response format enforced (JSON, no markdown wrapper)
- [ ] Temperature appropriate (0.85 for creativity, could lower for cost)

### 3. Engine Fallback Order (`modules/video/engines.py`)
- [ ] Cheapest engine tried first (Veo3 < Kling)
- [ ] Failed engine not retried unnecessarily
- [ ] `_get_available_engines()` checks key availability before attempting

### 4. Image Generation
- [ ] Safety fallback doesn't trigger excessive retries
- [ ] MASTER_STYLE not double-applied (check `safety.py`)
- [ ] Imagen preferred over DALL-E (2x cheaper)

### 5. Audio Pipeline
- [ ] Whisper called once per audio (not per cut)
- [ ] TTS generates single file (not per-cut)

## When to Use
Run this skill when:
- Adding new API calls to the pipeline
- Changing fallback/retry logic
- Optimizing for cost reduction
- Reviewing prompt token usage
