---
name: api-design
description: REST API design rules and SSE conventions for this project
---

# API Design Rules — AskAnything

## Endpoints

| Method | Path | Purpose | Response |
|--------|------|---------|----------|
| POST | /api/generate | Full pipeline | SSE stream |
| POST | /api/prepare | Preview (LLM+images) | SSE stream |
| POST | /api/render | Render from session | SSE stream |
| GET | /api/health | System status | JSON |
| GET | /api/key-usage | Per-key stats | JSON |
| POST | /api/batch/submit | Queue batch job | JSON |

## SSE Event Format
```json
{"type": "progress", "step": "image", "cut": 3, "total": 8, "message": "이미지 생성 중..."}
{"type": "image_ready", "cut": 3, "url": "/assets/session_id/cut_3.png"}
{"type": "complete", "video_url": "/assets/session_id/output.mp4"}
{"type": "error", "message": "API 오류가 발생했습니다"}
```

## Request Model Rules
1. All optional fields have sensible defaults
2. `cameraStyle` default: `"auto"` (not `"dynamic"`)
3. `language` default: `"ko"` with 18-language validation
4. `voiceId` nullable — auto-selects based on language if None
5. Use `Literal` types for enum-like fields
6. Validators in `PrepareRequest` must match `GenerateRequest`

## Response Conventions
- Success: return data directly (SSE or JSON)
- Error: `{"error": "message"}` with appropriate HTTP status
- Progress: SSE with `type: "progress"` and Korean messages
- Never expose internal errors or stack traces to client

## Adding New Endpoints
1. Define Pydantic request/response models
2. Add CORS if needed (explicit origins only)
3. Use `_generate_semaphore` if endpoint modifies env vars
4. Add to health check if endpoint depends on external service
5. Document in this skill and `codebase-overview`

## Versioning
- No API versioning currently (single client)
- Breaking changes: update frontend simultaneously
- Keep backward compatibility for batch queue schema
