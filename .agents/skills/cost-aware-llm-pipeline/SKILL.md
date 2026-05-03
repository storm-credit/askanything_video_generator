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

## Expertise Harness

### 1. Role Contract
비용 최적화 에이전트는 품질을 크게 떨어뜨리지 않는 선에서 중복 호출, cache miss, 비싼 fallback, 잘못된 비용 기록을 줄인다.

### 2. Inputs
- provider/model, token usage, cache hit state
- image/video/TTS engine selection, retry/fallback logs
- `modules/utils/cost_tracker.py` daily records

### 3. Expert Judgment Criteria
- 실제 API 성공 지점에서 비용을 기록한다.
- cache hit는 생성 비용으로 계산하지 않는다.
- 비싼 엔진 fallback은 품질/필요성 근거가 있어야 한다.

### 4. Hard Fail
- cache hit인데 API 비용을 기록.
- v2 orchestration 비용 누락.
- OpenAI disabled policy인데 OpenAI fallback 호출.
- 환율/가격표가 stale인데 production billing에 사용.

### 5. Auto-Fix Policy
- route-level count 추정보다 provider success hook 기록을 우선한다.
- provider/model/from_cache를 cost event에 포함한다.
- 가격 불명 모델은 warning + unknown tier로 분리한다.

### 6. Output Contract
- `cost_events`, `daily_total`, `by_provider`, `by_engine`, `warnings`

### 7. Code Wiring
- Tracker: `modules/utils/cost_tracker.py`
- Policy: `modules/utils/provider_policy.py`
- Routes: `routes/generate.py`, `routes/prepare.py`

### 8. Verification Harness
- Good: Imagen cache hit은 $0, 실제 생성만 image cost에 반영.
- Bad: 생성된 이미지 파일 개수만 보고 비용을 계산.
