# ✅ modules/video/ffmpeg.py
import os
from moviepy.editor import ImageClip, TextClip, AudioFileClip, CompositeVideoClip, concatenate_videoclips
from moviepy.config import change_settings

imagemagick_path = os.getenv("IMAGEMAGICK_BINARY", "C:\\Program Files\\ImageMagick-7.1.1-Q16-HDRI\\magick.exe")
change_settings({
    "IMAGEMAGICK_BINARY": imagemagick_path
})


def estimate_duration_by_text(text, wpm=150):
    """스크립트 길이에 따라 영상 길이(초) 추정"""
    words = len(text.split())
    return max(2, round((words / wpm) * 60, 1))  # 최소 2초 보장

def create_video(image_paths, audio_paths, scripts, topic_folder):
    clips = []

    for img_path, audio_path, script in zip(image_paths, audio_paths, scripts):
        if audio_path and os.path.exists(audio_path):
            audio_clip = AudioFileClip(audio_path)
            duration = audio_clip.duration
        else:
            duration = estimate_duration_by_text(script)
            audio_clip = None

        # 이미지 클립 생성
        img_clip = ImageClip(img_path).set_duration(duration)

        # 자막 클립 생성
        txt_clip = TextClip(
            script,
            fontsize=48,
            font="Arial",
            color="white",
            method='caption',
            size=img_clip.size
        ).set_duration(duration).set_position(("center", "bottom"))

        # 이미지, 자막 결합 및 오디오 추가
        composite = CompositeVideoClip([img_clip, txt_clip])
        if audio_clip:
            composite = composite.set_audio(audio_clip)
            
        clips.append(composite)

    # 모든 컷을 이어붙이기
    final_clip = concatenate_videoclips(clips, method="compose")

    # 저장 경로 생성
    output_dir = os.path.join("assets", topic_folder, "video")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "final_video.mp4")

    final_clip.write_videofile(output_path, fps=24, audio_codec="aac")

    return output_path
