# AskAnything Video Generator - 프로젝트 수행 계획서

이 문서는 프로젝트의 전체 진행 상황을 체크하는 현황판입니다.

## 🛠️ [Phase 1] 백엔드 모듈 고도화 (전문가 모델 적용) 및 검증
- [x] **기획 전문가 프롬프트 주입 (`cutter.py`)** : (v2 완) 역할 부여, 시간 제약, JSON 구조화 통제로 안정성 100% 확보
- [x] **마스터 아트 디렉터 스타일 주입 (`dalle.py`)** : (v2 완) 극한의 렌더링 강제 프리셋(8k, Octane Render) 및 API 재시도(Retry) 폭파 방지 로직 적용
- [x] **수석 영상 편집자 렌더링 엔진 구축 (`ffmpeg.py`)** : MoviePy 폐기. FFmpeg 켄번(Zoom) 효과, fps 고정, 자동 BGM 믹싱 추가 완료!
- [x] **내레이션 성우 교체 (`google.py`)** : gTTS 기계음 폐기 -> OpenAI 다큐멘터리 'Onyx' 보이스 도입 완.
- [x] **최종 백엔드 렌더링 테스트 (`test_pipeline.py`)** : 성공! (`final_video.mp4` 로컬 출력 완)

## 💻 [Phase 2] 상용화 프론트엔드 구축 (Next.js Apple Style)
- [x] **프로젝트 스캐폴딩** : `frontend/` 디렉토리에 Next.js + TailwindCSS + Framer Motion 뼈대 구축 완료
- [x] **메인 UI 컴포넌트 개발** : 글래스모피즘, 다크모드, 부드러운 인터랙션 애니메이션 페이지 구현 (`page.tsx`)
- [x] **백엔드 FastAPI 통로 구축** : Node.js 프론트엔드와 Python 백엔드를 실시간 통신(SSE)으로 연결 통로 공사 완료 (`api_server.py`)
- [ ] **최종 엔드투엔드(End-to-End) 검증** : (다음 단계) 웹 브라우저에서 버튼을 눌러 영상 생성 및 다운로드까지 전 과정 검증

## 🚀 [Phase 3] 깃허브 업로드 및 최종 런칭
- [/] **중간 백업 (Git Push)** : 1차 완성본 깃허브 업로드 (현재 진행 중)
- [ ] **민감 정보 가리기** : `.gitignore` 및 `.env` 파일 확실히 확인
- [ ] **최종 문서화** : `README.md` 최종 작성 및 런칭
