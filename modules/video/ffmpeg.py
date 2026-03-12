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

def create_dynamic_ass_for_cut(script, word_timestamps, duration, output_dir, index):
    ass_filename = f"cut_{index}.ass"
    ass_path = os.path.join(output_dir, ass_filename)
    
    # 숏폼 전용 다이내믹 캡션 (크고 두꺼운 노란색 아웃라인 폰트, 화면 하단-중앙)
    ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Malgun Gothic,140,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,12,10,2,20,20,600,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    def format_time(seconds):
        if seconds is None: seconds = 0.0
        h, m, s = int(seconds // 3600), int((seconds % 3600) // 60), int(seconds % 60)
        cs = int((seconds % 1) * 100)
        return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

    events = []
    
    if not word_timestamps:
        # 타임스탬프 없을 경우 기본 래핑 처리
        wrapped_script = "\\N".join(textwrap.wrap(script, width=12))
        events.append(f"Dialogue: 0,0:00:00.00,{format_time(duration)},Default,,0,0,0,,{wrapped_script}")
    else:
        # 단어를 2개씩 묶어서 빠르게 팝업 (Alex Hormozi 스타일)
        for i in range(0, len(word_timestamps), 2):
            chunk = word_timestamps[i:i+2]
            start_t = chunk[0].get('start', 0.0)
            end_t = chunk[-1].get('end', start_t + 0.5)
            text = " ".join([w.get('word', '') for w in chunk])
            
            # 애니메이션: 등장할 때 크기가 100% -> 115% 로 짧게 튀어오름 (Pop-up effect)
            text_ass = f"{{\\t(0,150,\\fscx115\\fscy115)}}{text}"
            events.append(f"Dialogue: 0,{format_time(start_t)},{format_time(end_t)},Default,,0,0,0,,{text_ass}")

    with open(ass_path, "w", encoding="utf-8-sig") as f:
        f.write(ass_content + "\n".join(events) + "\n")
        
    return ass_filename  

def create_video(image_paths, audio_paths, scripts, word_timestamps_list, topic_folder):
    output_dir = os.path.join("assets", topic_folder, "video")
    os.makedirs(output_dir, exist_ok=True)
    
    cut_videos = []
    cwd = os.path.abspath(output_dir)
    
    for i, (img_path, audio_path, script, word_timestamps) in enumerate(zip(image_paths, audio_paths, scripts, word_timestamps_list)):
        cut_video_filename = f"cut_{i}.mp4"
        
        duration = None
        if audio_path and os.path.exists(audio_path):
            duration = get_audio_duration(audio_path)
            
        if not duration:
            duration = estimate_duration_by_text(script)
            
        ass_filename = create_dynamic_ass_for_cut(script, word_timestamps, duration, output_dir, i)
        
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
