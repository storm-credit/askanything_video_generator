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
- Remotion: 24fps, 9:16 aspect ratio

## 🎼 오케스트라 에이전트 구조

이 프로젝트는 멀티채널 쇼츠 자동 생산 시스템. 각 서브에이전트는 전문가 롤로 동작.

### 기획팀 (스크립트 생성)
| 에이전트 | 롤 프롬프트 | 모델 | 위치 |
|---------|-----------|------|------|
| 스크립트 라이터 | "당신은 유튜브 쇼츠 바이럴 PD + 이미지 프롬프트 엔지니어입니다. 조회수 1000만 회 이상의 숏폼이 목표입니다." | Gemini Pro | cutter.py `_SYSTEM_PROMPT_*` |
| 비주얼 디렉터 | "You are a world-class visual director for viral YouTube Shorts. Your ONLY job is to rewrite image_prompts to maximize scroll-stopping power." | Gemini Flash | cutter.py `_enhance_image_prompts()` |
| 메타데이터 에디터 | 제목/설명/해시태그는 스크립트 라이터가 동시 생성 | Gemini Pro | cutter.py JSON 스키마 |

### 품질팀 (검증)
| 에이전트 | 롤 프롬프트 | 모델 | 위치 |
|---------|-----------|------|------|
| 하이네스 구조 검증 | Hook/충격체인/루프엔딩/감정아크 검증 + 자동 수정 | Gemini Flash | cutter.py `_verify_highness_structure()` |
| 주제 일치 검증 | "You are a strict visual consistency checker" — script↔image_prompt 피사체 일치 검증 | Gemini Flash | cutter.py `_verify_subject_match()` |
| 팩트 체커 | 스크립트 사실 정확성 검증 + 자동 수정 | Gemini Flash | cutter.py `_verify_facts()` |
| 글자수 가드 | 수정 후 30%+ 감소 거부, 15자 미만 거부 | 코드 | cutter.py 검증 루프 |
| 품질 게이트 | HARD FAIL 7개 조건 + 지역 스타일 검증 | 코드 | cutter.py `_validate_hard_fail()` |

### 제작팀 (영상 생성)
| 에이전트 | 역할 | 위치 |
|---------|------|------|
| 이미지 생성 | Imagen 4 + A/B 컷1 3장 | modules/image/imagen.py |
| TTS 성우 | ElevenLabs multilingual v2 | modules/tts/elevenlabs.py |
| 자막 추출 | Whisper word-level timestamps | modules/transcription/whisper.py |
| 렌더러 | Remotion 9:16 24fps | modules/video/remotion.py |

### 배포팀 (업로드)
| 에이전트 | 역할 | 위치 |
|---------|------|------|
| 스케줄러 | 채널별 시간 윈도우 분배 | modules/scheduler/time_planner.py |
| 자동 배포 | Day→생성→업로드 전체 파이프라인 | modules/scheduler/auto_deploy.py |
| 업로더 | YouTube 예약 업로드 (publishAt) | modules/upload/youtube.py |

### 분석팀 (성과)
| 에이전트 | 역할 | 위치 |
|---------|------|------|
| 통계 수집 | YouTube Data API v3 영상별 조회/좋아요 | modules/utils/youtube_stats.py |
| 주간 분석 | 카테고리별 성과, 상승/하락 패턴 | modules/scheduler/weekly_stats_update.py |

### 서브에이전트 호출 시 롤 규칙
- **Day 주제 생성**: "너는 멀티채널 쇼츠 주제 선정 전문가다. 채널별 성과 데이터 기반으로 인기 가능성 높은 주제만 선정한다."
- **성과 분석**: "너는 YouTube 쇼츠 데이터 분석가다. 채널별 조회수/카테고리/트렌드를 분석하고 주제 전략을 제안한다."
- **코드 리뷰**: "너는 시니어 Python/TypeScript 개발자다. 코드 재사용, 품질, 효율성을 검토하고 개선한다."
- **3D 전문가**: "너는 Blender bpy 자동화 + AI 3D 생성 전문가다. 쇼츠용 3D 비주얼 파이프라인을 설계한다." (Opus)

### Vertex AI 멀티 SA 키 (RPM 분산)
- shortspulse (메인), certain-upgrade (WonderDrop), exploratodo, endless-ripple (PrismTale)
- 429 시 자동 전환, 60초 블록 후 재시도
- 스크립트 = Pro, 검증/비주얼 디렉터 = Flash

## Git
- Branch: feature branches off main
- Commit messages: Korean description OK, conventional style preferred
- Never commit .env or API keys
