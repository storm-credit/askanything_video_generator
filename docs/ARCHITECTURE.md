# AskAnything Video Generator - Architecture

## 1. System Overview

```
[사용자 브라우저]          [백엔드 서버]              [외부 API]
  localhost:3000            localhost:8000
 ┌──────────────┐       ┌──────────────────┐      ┌────────────────┐
 │  Next.js     │──SSE──│  FastAPI          │──────│ OpenAI GPT-4o  │
 │  Frontend    │       │  api_server.py    │──────│ OpenAI DALL-E 3│
 │              │       │                  │──────│ OpenAI Whisper  │
 │  React +     │       │  Pipeline        │──────│ ElevenLabs TTS │
 │  Framer      │       │  Orchestrator    │──────│ Higgsfield API │
 │  Motion      │       │                  │──────│ Kling AI       │
 └──────────────┘       └────────┬─────────┘      └────────────────┘
                                 │
                         ┌───────▼─────────┐
                         │  Remotion (React)│
                         │  Video Renderer  │
                         │  (Node.js CLI)   │
                         └─────────────────┘
```

## 2. Pipeline Flow (비디오 생성 파이프라인)

```
[주제 입력] → [GPT 기획] → [DALL-E 이미지] → [비디오 엔진] → [TTS 음성] → [Whisper 자막] → [Remotion 렌더]
  "하늘은      6~10컷        컷별 이미지      이미지→영상      컷별 음성       단어 타임스탬프    최종 MP4
   왜 파래"    스크립트       1024x1792        5초 클립         MP3 파일        JSON 데이터       세로형 쇼츠
```

### 단계별 상세

| 단계 | 모듈 | 설명 | 진행률 |
|------|------|------|--------|
| 1. 기획 | `modules/gpt/cutter.py` | GPT-4o로 6~10컷 JSON 기획안 생성 (바이럴 스토리텔링 공식) | 10→30% |
| 2. 이미지 | `modules/image/dalle.py` | DALL-E 3로 컷별 시네마틱 이미지 생성 (1024x1792 세로) | 30→80% |
| 3. 비디오 | `modules/video/engines.py` | 선택된 엔진으로 이미지→5초 비디오 변환 | (병렬) |
| 4. 음성 | `modules/tts/elevenlabs.py` | ElevenLabs 다국어 v2로 내레이션 생성 | (병렬) |
| 5. 자막 | `modules/transcription/whisper.py` | Whisper API로 단어별 타임스탬프 추출 | (병렬) |
| 6. 렌더링 | `modules/video/remotion.py` | Remotion CLI로 최종 세로형 쇼츠 MP4 합성 | 85→100% |

### 병렬 처리 구조

```
단계 2~5는 컷별로 병렬 실행:

  컷 1: [DALL-E] → [비디오 엔진] → [TTS] → [Whisper]  ─┐
  컷 2: [DALL-E] → [비디오 엔진] → [TTS] → [Whisper]  ─┤
  컷 3: [DALL-E] → [비디오 엔진] → [TTS] → [Whisper]  ─┤──→ [Remotion 최종 렌더]
  ...                                                   ─┤
  컷 N: [DALL-E] → [비디오 엔진] → [TTS] → [Whisper]  ─┘

  asyncio.as_completed() + ThreadPoolExecutor로 동시 처리
```

## 3. Directory Structure

```
askanything_video_generator/
├── api_server.py              # FastAPI 메인 서버 (SSE 스트리밍)
├── .env                       # API 키 설정 (gitignored)
├── .env.example               # 환경변수 템플릿
├── CLAUDE.md                  # Claude Code 프로젝트 규칙
│
├── modules/                   # Python 백엔드 모듈
│   ├── gpt/
│   │   ├── cutter.py          # GPT 기획 (6~10컷 JSON)
│   │   └── search.py          # Tavily 팩트체크 검색 (RAG)
│   ├── image/
│   │   └── dalle.py           # DALL-E 3 이미지 생성
│   ├── tts/
│   │   └── elevenlabs.py      # ElevenLabs TTS 음성
│   ├── transcription/
│   │   └── whisper.py         # Whisper 단어 타임스탬프
│   ├── video/
│   │   ├── engines.py         # 멀티 비디오 엔진 통합 (Higgsfield)
│   │   ├── kling.py           # Kling AI 직접 연동 (폴백)
│   │   └── remotion.py        # Remotion CLI 호출
│   └── utils/
│       └── slugify.py         # 토픽 → 폴더명 변환
│
├── frontend/                  # Next.js 프론트엔드
│   └── src/app/
│       ├── page.tsx           # 메인 UI (입력, 엔진 선택, 진행률, 에러)
│       ├── layout.tsx         # 레이아웃
│       └── globals.css        # 글로벌 스타일
│
├── remotion/                  # Remotion 비디오 렌더러
│   └── src/
│       ├── index.ts           # Remotion 진입점
│       ├── Main.tsx           # 메인 컴포지션 (프레임 계산)
│       ├── Cut.tsx            # 개별 컷 컴포넌트
│       └── Captions.tsx       # 호르모지 스타일 자막
│
├── assets/                    # 생성된 파일 (topic별 폴더)
│   └── {topic_folder}/
│       ├── images/            # DALL-E 이미지 (cut_00.png ...)
│       ├── audio/             # TTS 음성 (cut_0.mp3 ...)
│       ├── video_clips/       # 비디오 클립 (kling_cut_00.mp4 ...)
│       └── video/
│           ├── remotion_props.json  # Remotion 입력 데이터
│           └── final_shorts.mp4     # 최종 출력 비디오
│
├── .claude/                   # Claude Code 설정
│   ├── launch.json            # 서버 실행 설정
│   ├── settings.json          # 훅 설정
│   └── skills/                # 재사용 스킬
└── docs/
    └── ARCHITECTURE.md        # 이 문서
```

## 4. API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | API 상태 확인 |
| GET | `/api/engines` | 사용 가능한 비디오 엔진 목록 |
| GET | `/api/health` | 필수 API 키 검증 상태 |
| POST | `/api/generate` | 비디오 생성 (SSE 스트리밍) |

### SSE 프로토콜

| Prefix | 설명 | 예시 |
|--------|------|------|
| `PROG\|N` | 진행률 (0~100) | `PROG\|30` |
| `DONE\|path` | 완료 + 다운로드 경로 | `DONE\|/assets/topic/video/final.mp4` |
| `ERROR\|msg` | 에러 메시지 | `ERROR\|[인증 오류] API 키가 유효하지 않습니다` |
| (텍스트) | 실시간 로그 | `[기획 완료] 총 8컷 기획 완료!` |

## 5. Video Engine Architecture

```
사용자 선택 (프론트엔드 드롭다운)
       │
       ▼
  engines.py (라우터)
       │
       ├── kling ──→ Higgsfield API ──→ 실패 시 ──→ Kling 직접 API (kling.py)
       ├── sora2 ──→ OpenAI Sora 2 API
       ├── veo3  ──→ Higgsfield API
       ├── hailuo ─→ Higgsfield API
       ├── wan   ──→ Higgsfield API
       └── none  ──→ (이미지만 사용, 비디오 변환 건너뜀)
```

## 6. Error Handling Flow

```
[사전 검증]                    [실행 중 에러]                [프론트엔드 표시]
 ┌─────────────┐              ┌──────────────┐             ┌──────────────┐
 │ API 키 존재? │──No──→      │ 401 인증 실패 │──→          │ 빨간색 에러   │
 │ 엔진 유효?   │              │ 429 할당량    │──→          │ 로그 + 에러   │
 │ topic 비어?  │              │ 타임아웃      │──→          │ 결과 카드     │
 │ Pydantic 검증│              │ 네트워크 끊김 │──→          │ (구체적 메시지)│
 └─────────────┘              │ 컷별 실패 추적│──→          └──────────────┘
                              └──────────────┘
```

### 검증 체크리스트

| 검증 항목 | 위치 | 설명 |
|-----------|------|------|
| topic 빈값/공백 | Pydantic validator | 1~500자 제한 |
| videoEngine 유효성 | Pydantic validator | 허용 목록 체크 |
| OpenAI API Key | `_validate_keys()` | 필수 |
| ElevenLabs API Key | `_validate_keys()` | 필수 |
| Higgsfield/Kling Key | `_validate_keys()` | 엔진 선택 시 필수 |
| GPT 응답 구조 | `cutter.py` | choices 존재, JSON 파싱, cuts 유효성 |
| 이미지 다운로드 | `dalle.py` | 타임아웃 30초, 3회 재시도 |
| TTS 텍스트 비어있음 | `elevenlabs.py` | 빈 텍스트 차단 |
| 오디오 파일 크기 | `whisper.py` | 0바이트 파일 차단 |
| Remotion 프로세스 | `remotion.py` | 10분 타임아웃, stderr 캡처 |
| 컷별 실패 추적 | `api_server.py` | 어느 컷이 실패했는지 구체적 보고 |

## 7. Tech Stack

| 영역 | 기술 |
|------|------|
| Frontend | Next.js 16, React, TypeScript, Tailwind CSS, Framer Motion |
| Backend | Python, FastAPI, Uvicorn, SSE (Server-Sent Events) |
| Video Render | Remotion 4 (React → MP4), FFmpeg |
| AI Services | OpenAI (GPT-4o, DALL-E 3, Whisper, Sora 2), ElevenLabs, Higgsfield, Kling AI |
| Infra | Claude Code (Skills, Hooks, launch.json) |
