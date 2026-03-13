import os
import json
import subprocess


def _validate_inputs(visual_paths, audio_paths, scripts, word_timestamps_list):
    if not (len(visual_paths) == len(audio_paths) == len(scripts) == len(word_timestamps_list)):
        raise ValueError("Remotion 입력 배열 길이가 서로 다릅니다.")

    for idx, (v, a) in enumerate(zip(visual_paths, audio_paths), start=1):
        if not v or not os.path.exists(v):
            raise FileNotFoundError(f"컷 {idx} visual 파일이 없습니다: {v}")
        if not a or not os.path.exists(a):
            raise FileNotFoundError(f"컷 {idx} audio 파일이 없습니다: {a}")


def create_remotion_video(visual_paths, audio_paths, scripts, word_timestamps_list, topic_folder):
    """
    Python 백엔드 데이터를 모아 Remotion (React) 렌더링 CLI로 넘겨서 최종 비디오를 합성합니다.
    """
    try:
        _validate_inputs(visual_paths, audio_paths, scripts, word_timestamps_list)
    except Exception as e:
        print(f"[Remotion 입력 검증 실패] {e}")
        return None

    output_dir = os.path.join("assets", topic_folder, "video")
    os.makedirs(output_dir, exist_ok=True)

    final_video_path = os.path.join(output_dir, "final_shorts.mp4")
    props_json_path = os.path.join(output_dir, "remotion_props.json")

    cuts_data = []
    total_duration_in_frames = 0
    fps = 24

    for visual_path, audio_path, _script, word_timestamps in zip(
        visual_paths, audio_paths, scripts, word_timestamps_list
    ):
        # Whisper 타임스탬프 중 마지막 단어 기준으로 컷 길이 계산 (단어가 없을 시 기본값 5초)
        duration_sec = 5.0
        if word_timestamps and len(word_timestamps) > 0:
            duration_sec = max(1.5, word_timestamps[-1].get("end", 0) + 0.3)

        frames = int(duration_sec * fps)
        total_duration_in_frames += frames

        cuts_data.append(
            {
                "visual_path": os.path.abspath(visual_path).replace("\\", "/"),
                "audio_path": os.path.abspath(audio_path).replace("\\", "/"),
                "word_timestamps": word_timestamps or [],
                "duration_in_frames": frames,
            }
        )

    props_data = {"cuts": cuts_data, "totalDurationInFrames": total_duration_in_frames}

    with open(props_json_path, "w", encoding="utf-8") as f:
        json.dump(props_data, f, ensure_ascii=False, indent=2)

    remotion_dir = os.path.abspath("remotion")
    if not os.path.exists(os.path.join(remotion_dir, "node_modules")):
        print("[Remotion 렌더링 실패] remotion/node_modules가 없습니다. `npm --prefix remotion install` 실행 필요")
        return None

    cmd = [
        "npx",
        "remotion",
        "render",
        "src/index.ts",
        "Main",
        os.path.abspath(final_video_path),
        "--props",
        os.path.abspath(props_json_path),
    ]

    print(f"-> [Remotion 렌더링 마스터] 총 길이 {total_duration_in_frames} 프레임, 렌더링 준비 완료.")

    try:
        # Windows에서는 shell=True가 안정적, Unix에서는 False 권장
        shell_mode = os.name == "nt"
        result = subprocess.run(
            cmd, cwd=remotion_dir, check=True, shell=shell_mode,
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=600,
        )

        if not os.path.exists(final_video_path):
            print(f"[Remotion 렌더링 실패] 렌더 명령은 끝났지만 결과 파일이 없습니다: {final_video_path}")
            if result.stderr:
                print(f"  stderr: {result.stderr[:500]}")
            return None
        return final_video_path

    except subprocess.TimeoutExpired:
        print("[Remotion 렌더링 실패] 10분 타임아웃 초과. 렌더링이 너무 오래 걸립니다.")
        return None
    except subprocess.CalledProcessError as e:
        print(f"[Remotion 렌더링 실패] 종료 코드: {e.returncode}")
        if e.stderr:
            print(f"  stderr: {e.stderr[:500]}")
        return None
