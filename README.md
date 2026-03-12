# AskAnything Video Generator

AskAnything 주제를 입력하면 **기획(GPT) → 리서치(Tavily) → 이미지(DALL·E) → 모션(Kling) → 내레이션(ElevenLabs) → 동적자막(Remotion)** 순서로 쇼츠 영상을 자동 생성하는 파이프라인입니다.

## 현재 기준 파이프라인 (Phase 4)
- **Fact-first 기획**: Tavily 검색 근거를 활용해 할루시네이션 최소화
- **고품질 성우 음성**: ElevenLabs 기반 다큐멘터리 톤 내레이션
- **시네마틱 컷 모션화**: Kling 연동으로 정지 이미지를 모션 비디오로 확장
- **Alex Hormozi 스타일 자막**: Remotion(React) 기반 동적 자막 렌더링

## 빠른 실행

### 1) Python 의존성 설치
```bash
pip install -r requirements.txt
```

### 2) Remotion 의존성 설치
```bash
npm --prefix remotion install
```

### 3) API 서버 실행
```bash
python api_server.py
```

## 트러블슈팅 (3컷 고정 / final_video.mp4 404)
아래 순서대로 점검하면 대부분 복구됩니다.

1. **서버 완전 재시작** (구버전 프로세스 캐시 제거)
   ```bash
   pkill -f api_server.py || true
   python api_server.py
   ```
2. **Remotion 설치 상태 확인**
   ```bash
   npm --prefix remotion install
   npx --prefix remotion remotion --help
   ```
3. **컷 수 정책 확인 (6~10컷)**
   - `modules/gpt/cutter.py`의 프롬프트/검증 로직 확인
4. **최종 파일 경로 확인**
   - 렌더 직후 `final_video.mp4` 생성 위치와 다운로드 엔드포인트가 같은 파일을 가리키는지 확인

## 권장 운영 점검 명령어
```bash
python -m py_compile api_server.py modules/gpt/cutter.py modules/video/remotion.py modules/video/kling.py modules/tts/elevenlabs.py
```

## 프로젝트 주요 경로
- `api_server.py`: FastAPI 서버 및 다운로드/생성 API
- `modules/gpt/cutter.py`: 컷 분할/스토리 기획
- `modules/gpt/search.py`: Tavily 검색 통합
- `modules/video/kling.py`: Kling API 연동
- `modules/video/remotion.py`: Remotion 렌더 오케스트레이션
- `modules/tts/elevenlabs.py`: ElevenLabs 음성 합성
- `PROJECT_PLAN.md`: 단계별 마스터 플랜 및 운영 체크리스트
