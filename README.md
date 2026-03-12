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