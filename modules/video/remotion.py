import os
import json
import subprocess

def create_remotion_video(visual_paths, audio_paths, scripts, word_timestamps_list, topic_folder):
    """
    Python 백엔드 데이터를 모아 Remotion (React) 렌더링 CLI로 넘겨서 최종 비디오를 합성합니다.
    """
    output_dir = os.path.join("assets", topic_folder, "video")
    os.makedirs(output_dir, exist_ok=True)
    
    final_video_path = os.path.join(output_dir, "final_shorts.mp4")
    props_json_path = os.path.join(output_dir, "remotion_props.json")
    
    cuts_data = []
    total_duration_in_frames = 0
    fps = 24
    
    for i, (visual_path, audio_path, script, word_timestamps) in enumerate(zip(visual_paths, audio_paths, scripts, word_timestamps_list)):
        # Whisper 타임스탬프 중 마지막 단어 기준으로 컷 길이 계산 (단어가 없을 시 기본값 5초)
        duration_sec = 5.0
        if word_timestamps and len(word_timestamps) > 0:
            duration_sec = word_timestamps[-1]['end'] + 0.3 # 0.3초 패딩
            
        frames = int(duration_sec * fps)
        total_duration_in_frames += frames
        
        cuts_data.append({
            "visual_path": os.path.abspath(visual_path).replace("\\", "/"),
            "audio_path": os.path.abspath(audio_path).replace("\\", "/"),
            "word_timestamps": word_timestamps,
            "duration_in_frames": frames
        })
        
    props_data = {
        "cuts": cuts_data,
        "totalDurationInFrames": total_duration_in_frames
    }

    with open(props_json_path, "w", encoding="utf-8") as f:
        json.dump(props_data, f, ensure_ascii=False, indent=2)

    remotion_dir = os.path.abspath("remotion")
    
    # Remotion CLI 호출 명령어
    cmd = [
        "npx", "remotion", "render", 
        "src/index.ts", "Main", 
        os.path.abspath(final_video_path), 
        "--props", os.path.abspath(props_json_path)
    ]
    
    print(f"-> [Remotion 렌더링 마스터] 총 길이 {total_duration_in_frames} 프레임, 렌더링 준비 완료.")
    
    try:
        # Windows 환경 npx 실행 (shell=True 필수)
        subprocess.run(cmd, cwd=remotion_dir, check=True, shell=True)
        return final_video_path
        
    except subprocess.CalledProcessError as e:
        print(f"[Remotion 렌더링 실패] {e}")
        return None
