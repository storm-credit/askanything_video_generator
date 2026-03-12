import streamlit as st
import sys
import os
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()

# 🔁 시스템 경로에 상위 디렉토리 추가 (모듈 import 용도)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 📦 커스텀 모듈 import
from modules.gpt.cutter import generate_cuts
from modules.image.dalle import generate_image
from modules.tts.google import generate_tts  # ✅ 오디오 생성 모듈
from modules.utils.slugify import slugify_topic
from modules.video.ffmpeg import create_video  # ✅ 영상 생성 모듈

# 🖥️ Streamlit 설정
st.set_page_config(page_title="AskAnything 컷 생성기", layout="centered")
st.title("📋 AskAnything 컷 & 스크립트 생성기")
st.markdown("💡 **영상 흐름에 따라 컷 수는 자동으로 결정**됩니다.")

# 🔹 사용자 입력
topic = st.text_input("주제를 입력하세요", "벌은 잠을 잘까?")

if st.button("생성 시작"):
    # ✅ 자동 컷 생성
    cuts, topic_folder = generate_cuts(topic)
    st.success(f"총 {len(cuts)}컷 생성 완료!")

    # ✅ 저장 폴더 구성
    base_path = os.path.join("assets", topic_folder)
    os.makedirs(os.path.join(base_path, "images"), exist_ok=True)
    os.makedirs(os.path.join(base_path, "script"), exist_ok=True)
    os.makedirs(os.path.join(base_path, "video"), exist_ok=True)

    image_paths = []
    audio_paths = []
    scripts = []
    progress_bar = st.progress(0)

    # ✅ 이미지 및 스크립트 생성 반복
    for i, cut in enumerate(cuts):
        st.text(f"컷 {i+1}: {cut.get('text', '')}")
        prompt_text = cut.get("prompt", "").strip()
        if not prompt_text:
            st.warning(f"컷 {i+1}: 프롬프트 누락 → 건너뜀")
            continue

        try:
            image_path = generate_image(prompt_text, i, topic_folder)
        except Exception as e:
            st.warning(f"컷 {i+1} 이미지 생성 실패: {e}")
            continue

        script_text = cut.get("script", "").strip()
        if not script_text:
            script_text = f"{cut.get('text', '')}에 대한 설명입니다."

        try:
            audio_path = generate_tts(script_text, i, topic_folder)
        except Exception as e:
            st.warning(f"컷 {i+1} 오디오 생성 실패: {e}")
            audio_path = None

        image_paths.append(image_path)
        audio_paths.append(audio_path)
        scripts.append(script_text)

        progress_bar.progress((i + 1) / len(cuts))

    # ✅ 스크립트 저장
    script_path = os.path.join(base_path, "script", "scripts.txt")
    with open(script_path, "w", encoding="utf-8") as f:
        for i, script in enumerate(scripts):
            f.write(f"{i+1:02}: {script}\n")

    # ✅ 스크립트 다운로드 버튼
    with open(script_path, "r", encoding="utf-8") as f:
        st.download_button("자막용 스크립트 다운로드", f, file_name="scripts.txt")

    # ✅ 영상 자동 생성
    video_path = create_video(image_paths, audio_paths, scripts, topic_folder)
    if video_path:
        with open(video_path, "rb") as f:
            st.download_button("최종 영상 다운로드", f, file_name="final.mp4")

    st.success("🎉 이미지, 스크립트 및 영상 생성 완료! 편집 도구 없이 곧바로 활용 가능합니다.")
