import os
import subprocess
import textwrap

def estimate_duration_by_text(text, wpm=150):
    words = len(text.split())
    return max(2, round((words / wpm) * 60, 1))

def get_audio_duration(audio_path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path
    ]
    try:
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        return float(result.stdout.strip())
    except:
        return None

def create_ass_for_cut(script, output_dir, index):
    ass_filename = f"cut_{index}.ass"
    ass_path = os.path.join(output_dir, ass_filename)
    
    # 세로형 쇼츠를 위해 글자 래핑 짧게 (12자)
    wrapped_script = "\\N".join(textwrap.wrap(script, width=12))
    
    # ASS 포맷 (K-Pop 쇼츠 스타일 트렌디 자막 - 노란색, 두꺼운 그림자)
    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Malgun Gothic,110,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,8,6,2,10,10,400,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:59:59.99,Default,,0,0,0,,{wrapped_script}
"""
    with open(ass_path, "w", encoding="utf-8-sig") as f:
        f.write(ass_content)
        
    return ass_filename  

def create_video(image_paths, audio_paths, scripts, topic_folder):
    output_dir = os.path.join("assets", topic_folder, "video")
    os.makedirs(output_dir, exist_ok=True)
    
    cut_videos = []
    cwd = os.path.abspath(output_dir)
    
    for i, (img_path, audio_path, script) in enumerate(zip(image_paths, audio_paths, scripts)):
        cut_video_filename = f"cut_{i}.mp4"
        
        duration = None
        if audio_path and os.path.exists(audio_path):
            duration = get_audio_duration(audio_path)
            
        if not duration:
            duration = estimate_duration_by_text(script)
            
        ass_filename = create_ass_for_cut(script, output_dir, i)
        
        # FFmpeg 기반 렌더링 호출 (Zoom-in 켄번 효과 + ASS 자막)
        img_abs = os.path.abspath(img_path)
        
        # 1.0 -> 1.15 로 서서히 줌인되는 필터 (fps=24 강제 고정으로 잔상 방지)
        fps = 24
        frames = int(duration * fps)
        zoom_filter = f"zoompan=z='min(zoom+0.0015,1.15)':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps={fps}"
        
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", img_abs
        ]
        
        if audio_path and os.path.exists(audio_path):
            cmd.extend(["-i", os.path.abspath(audio_path)])
            
        cmd.extend([
            "-vf", f"{zoom_filter},ass='{ass_filename}'",
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", cut_video_filename
        ])
        
        print(f"-> [편집 전문가] 컷 {i+1} 렌더링 (Zoom-in & 자막) 중...")
        subprocess.run(cmd, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cut_videos.append(cut_video_filename)
        
    # Concat
    concat_filename = "concat.txt"
    concat_filepath = os.path.join(cwd, concat_filename)
    with open(concat_filepath, "w", encoding="utf-8") as f:
        for cv in cut_videos:
            f.write(f"file '{cv}'\n")
            
    final_output_filename = "final_video.mp4"
    final_output_path = os.path.join(cwd, final_output_filename)
    
    concat_cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_filename,
        "-c", "copy",
        final_output_filename
    ]
    
    print("-> [편집 전문가] 컷 연결 및 최종 영상 병합 중...")
    subprocess.run(concat_cmd, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # ✅ 시네마틱 BGM 오디오 믹싱 처리 (상용화 기술)
    # 루트 폴더의 assets/bgm.mp3 파일이 존재하면 자동으로 배경음악을 깔아줌
    bgm_path = os.path.abspath(os.path.join("assets", "bgm.mp3"))
    if os.path.exists(bgm_path):
        mixed_output_filename = "final_video_with_bgm.mp4"
        mixed_output_path = os.path.join(cwd, mixed_output_filename)
        
        mix_cmd = [
            "ffmpeg", "-y",
            "-i", final_output_path,
            "-stream_loop", "-1", "-i", bgm_path, # BGM 무한 반복 (가장 긴 비디오에 맞춤)
            "-filter_complex", "[0:a]volume=1.0[a1];[1:a]volume=0.15[a2];[a1][a2]amix=inputs=2:duration=first:dropout_transition=2[a]",
            "-map", "0:v", "-map", "[a]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            mixed_output_path
        ]
        print("-> [음향 감독] 시네마틱 BGM 믹싱 완료!")
        subprocess.run(mix_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return mixed_output_path
    
    return final_output_path
