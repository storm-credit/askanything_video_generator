import os
import json
import subprocess


def _validate_cut_assets(visual_paths, audio_paths):
    for i, (visual_path, audio_path) in enumerate(zip(visual_paths, audio_paths), start=1):
        if not visual_path or not os.path.exists(visual_path):
            raise FileNotFoundError(f"컷 {i} visual 파일이 없거나 경로가 비어 있습니다: {visual_path}")
        if not audio_path or not os.path.exists(audio_path):
            raise FileNotFoundError(f"컷 {i} audio 파일이 없거나 경로가 비어 있습니다: {audio_path}")


def _check_remotion_install(remotion_dir):
    package_json = os.path.join(remotion_dir, "package.json")
    node_modules = os.path.join(remotion_dir, "node_modules")
    if not os.path.exists(package_json):
        raise FileNotFoundError("remotion/package.json 파일이 없습니다.")
    if not os.path.exists(node_modules):
        raise RuntimeError("Remotion 의존성이 설치되지 않았습니다. remotion 폴더에서 'npm install'을 실행하세요.")

def create_remotion_video(visual_paths, audio_paths, scripts, word_timestamps_list, topic_folder):
    """
    Python 백엔드 데이터를 모아 Remotion (React) 렌더링 CLI로 넘겨서 최종 비디오를 합성합니다.
    """
    if not (len(visual_paths) == len(audio_paths) == len(scripts) == len(word_timestamps_list)):
        raise ValueError("Remotion 입력 배열 길이가 서로 다릅니다.")

    _validate_cut_assets(visual_paths, audio_paths)

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
    _check_remotion_install(remotion_dir)
    
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

        if not os.path.exists(final_video_path):
            raise FileNotFoundError(f"Remotion 렌더 완료 후 결과 파일이 없습니다: {final_video_path}")

        return final_video_path
        
    except subprocess.CalledProcessError as e:
        print(f"[Remotion 렌더링 실패] {e}")
        return None
