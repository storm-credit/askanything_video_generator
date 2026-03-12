# AskAnything Video Generator

이 프로젝트는 어린이 대상 과학 궁금증을 해결해주는 짧은 세로형 영상(쇼츠/릴스 형식)을 자동으로 생성하는 파이썬 기반 웹 애플리케이션입니다.
주제를 입력하면 GPT가 스크립트와 이미지 프롬프트를 작성하고, DALL-E로 그림을 그리고, Google TTS로 음성을 만들어 최종 영상을 합성합니다.

## 주요 기능
- **GPT 기반 컷 분할**: 입력된 주제에 맞춰 필요한 만큼의 컷(장면)을 자동 구성
- **자동 이미지 생성**: DALL-E 3를 이용해 각 장면에 맞는 9:16 비율 세로형 이미지 생성
- **자동 음성(TTS) 생성**: Google TTS를 통해 스크립트를 음성으로 변환
- **자동 비디오 합성**: MoviePy 패키지를 이용해 이미지, 음성, 자막을 하나로 합쳐 MP4 영상 생성
- **Streamlit 웹 UI**: 브라우저에서 간편하게 주제를 입력하고 생성 과정을 확인 가능

## 필수 환경
- Python 3.9 이상
- [ImageMagick](https://imagemagick.org/script/download.php) (자막 생성을 위해 필수)
  - 설치 후 `.env` 파일에 `IMAGEMAGICK_BINARY` 경로를 맞춰주세요.

## 설치 및 실행 방법

1. **패키지 설치**
   ```bash
   pip install -r requirements.txt
   ```

2. **환경 변수 설정**
   루트 디렉토리에 `.env` 파일을 새로 만들고, 아래와 같이 본인의 환경에 맞게 입력합니다. (`.env.example` 참고)
   ```env
   OPENAI_API_KEY="sk-proj-본인의_API_키"
   OPENAI_MODEL="gpt-4o"
   IMAGEMAGICK_BINARY="C:\Program Files\ImageMagick-7.1.1-Q16-HDRI\magick.exe"
   ```

3. **앱 실행**
   ```bash
   streamlit run app/main.py
   ```

## 프로젝트 경로 구조
- `app/main.py`: Streamlit 기반 웹 UI 및 메인 실행 로직
- `modules/gpt/cutter.py`: GPT API를 이용한 컷 분할 및 스크립트 기획 모듈
- `modules/image/dalle.py`: DALL-E 3를 이용한 쇼츠용 세로형 이미지 생성
- `modules/tts/google.py`: Google TTS 오디오 변환
- `modules/video/ffmpeg.py`: MoviePy + ImageMagick을 이용해 이미지, 자막, 오디오를 병합해 최종 영상 합성
## FastAPI + Remotion 트러블슈팅 체크리스트 (404 / 컷 수 부족 대응)

아래 순서대로 점검하면 `3컷만 생성`, `final video 404` 문제를 빠르게 분리할 수 있습니다.

1. **서버 코드 최신 반영 확인**
   ```bash
   pkill -f api_server.py || true
   python api_server.py
   ```

2. **Remotion 의존성 설치 확인**
   ```bash
   cd remotion
   npm install
   cd ..
   ```

3. **사전 진단 API 실행 (신규)**
   ```bash
   curl -s http://localhost:8000/api/preflight
   ```
   - `ready: true`여야 렌더 준비 완료입니다.
   - `remotion_node_modules: false`면 `npm install`이 누락된 상태입니다.

4. **컷 수 규격 확인**
   - 현재 파이프라인은 `6~10컷`이 아니면 자동 재요청 후, 그래도 실패 시 에러를 발생시킵니다.
   - 즉, 3~4컷으로 내려앉는 문제를 서버 레벨에서 차단합니다.

## "동시버전 4"(= GPT-4 계열) 사용 시 장점

질문하신 "동시버전 4"는 보통 `OPENAI_MODEL=gpt-4o` 또는 GPT-4 계열 모델 사용을 의미합니다.

- **장점**
  - 프롬프트 규칙(컷 수, JSON 스키마) 준수율이 상대적으로 높습니다.
  - 사실 기반 설명/문맥 유지가 더 안정적입니다.
  - 쇼츠용 문장 톤(후킹 → 빌드업 → 결말) 일관성이 좋아집니다.

- **주의점**
  - 모델을 바꾼다고 100% 해결되진 않습니다.
  - 그래서 현재 코드는 모델 성능 + 서버 강제 검증(6~10컷) 두 겹으로 막도록 보강되어 있습니다.
