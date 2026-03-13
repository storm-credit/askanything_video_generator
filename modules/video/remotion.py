import os
import re
import json
import shutil
import subprocess
from datetime import datetime

# 브랜드 이미지 (brand/ → assets/로 자동 복사하여 Remotion에서 접근)
BRAND_DIR = "brand"
INTRO_IMAGE = "intro.png"
OUTRO_IMAGE = "outro.jpg"
BGM_FILE = "bgm.mp3"
INTRO_DURATION_FRAMES = 24         # 1초 @ 24fps
OUTRO_DURATION_FRAMES = 24         # 1초 @ 24fps


def _to_relative(p: str) -> str:
    """assets/ 기준 상대 경로 변환 (staticFile()용 - publicDir=assets/)"""
    normed = p.replace("\\", "/")
    idx = normed.find("assets/")
    return normed[idx + len("assets/"):] if idx >= 0 else normed


def _validate_inputs(visual_paths: list[str], audio_paths: list[str], scripts: list[str], word_timestamps_list: list[list[dict]]) -> None:
    if not (len(visual_paths) == len(audio_paths) == len(scripts) == len(word_timestamps_list)):
        raise ValueError("Remotion 입력 배열 길이가 서로 다릅니다.")

    for idx, (v, a) in enumerate(zip(visual_paths, audio_paths), start=1):
        if not v or not os.path.exists(v):
            raise FileNotFoundError(f"컷 {idx} visual 파일이 없습니다: {v}")
        if not a or not os.path.exists(a):
            raise FileNotFoundError(f"컷 {idx} audio 파일이 없습니다: {a}")


def create_remotion_video(visual_paths: list[str], audio_paths: list[str], scripts: list[str], word_timestamps_list: list[list[dict]], topic_folder: str, title: str = "") -> str | None:
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

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_video_path = os.path.join(output_dir, f"{topic_folder}_{timestamp}.mp4")
    props_json_path = os.path.join(output_dir, "remotion_props.json")

    cuts_data = []
    total_duration_in_frames = 0
    fps = 24

    for visual_path, audio_path, _script, word_timestamps in zip(
        visual_paths, audio_paths, scripts, word_timestamps_list
    ):
        # Whisper 타임스탬프 중 마지막 단어 기준으로 컷 길이 계산 (단어가 없을 시 기본값 5초)
        duration_sec = 5.0
        if word_timestamps:
            duration_sec = max(1.5, word_timestamps[-1].get("end", 0) + 0.3)

        frames = int(duration_sec * fps)
        total_duration_in_frames += frames

        cuts_data.append(
            {
                "visual_path": _to_relative(visual_path),
                "audio_path": _to_relative(audio_path),
                "word_timestamps": word_timestamps or [],
                "duration_in_frames": frames,
            }
        )

    # 브랜드 이미지: brand/ → assets/로 복사 (Remotion publicDir = assets/)
    intro_image_path = None
    outro_image_path = None

    for asset_name in [INTRO_IMAGE, OUTRO_IMAGE, BGM_FILE]:
        brand_src = os.path.join(BRAND_DIR, asset_name)
        assets_dst = os.path.join("assets", asset_name)
        if os.path.exists(brand_src):
            shutil.copy2(brand_src, assets_dst)

    if os.path.exists(os.path.join("assets", INTRO_IMAGE)):
        intro_image_path = INTRO_IMAGE
        total_duration_in_frames += INTRO_DURATION_FRAMES
        print(f"-> [인트로] 브랜드 인트로 {INTRO_DURATION_FRAMES}프레임 (1초) 추가")

    # 제목: 첫 번째 컷 위 오버레이로 표시 (별도 시간 추가 없음)
    if title:
        print(f"-> [제목] '{title}' — 첫 컷 위 오버레이로 표시")

    if os.path.exists(os.path.join("assets", OUTRO_IMAGE)):
        outro_image_path = OUTRO_IMAGE
        total_duration_in_frames += OUTRO_DURATION_FRAMES
        print(f"-> [아웃트로] 브랜드 아웃트로 {OUTRO_DURATION_FRAMES}프레임 (1초) 추가")

    # BGM: brand/bgm.mp3 → 전체 영상 배경음악 (있을 때만)
    bgm_path = None
    if os.path.exists(os.path.join("assets", BGM_FILE)):
        bgm_path = BGM_FILE
        print(f"-> [BGM] 배경음악 '{BGM_FILE}' 전체 영상에 적용")

    props_data = {
        "cuts": cuts_data,
        "totalDurationInFrames": total_duration_in_frames,
        "introImagePath": intro_image_path,
        "outroImagePath": outro_image_path,
        "bgmPath": bgm_path,
        "title": title or None,
    }

    with open(props_json_path, "w", encoding="utf-8") as f:
        json.dump(props_data, f, ensure_ascii=False, indent=2)

    remotion_dir = os.path.abspath("remotion")
    if not os.path.exists(os.path.join(remotion_dir, "node_modules")):
        print("[Remotion 렌더링 실패] remotion/node_modules가 없습니다. `npm --prefix remotion install` 실행 필요")
        return None

    # 입력 검증: topic_folder에 위험 문자가 없는지 확인 (shell injection 방지)
    if not re.match(r'^[\w\-]+$', topic_folder):
        print(f"[Remotion 보안 오류] topic_folder에 허용되지 않는 문자가 포함됨: {topic_folder}")
        return None

    assets_dir = os.path.abspath("assets")
    abs_video_path = os.path.abspath(final_video_path)
    abs_props_path = os.path.abspath(props_json_path)

    cmd = [
        "npx",
        "remotion",
        "render",
        "src/index.ts",
        "Main",
        abs_video_path,
        "--props",
        abs_props_path,
        "--public-dir",
        assets_dir,
    ]

    print(f"-> [Remotion 렌더링 마스터] 총 길이 {total_duration_in_frames} 프레임, 렌더링 준비 완료.")

    try:
        # Windows: shell=True 필요하지만 list → 문자열로 변환 (공백 경로 안전 처리)
        if os.name == "nt":
            cmd_str = subprocess.list2cmdline(cmd)
            result = subprocess.run(
                cmd_str, cwd=remotion_dir, check=True, shell=True,
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=600,
            )
        else:
            result = subprocess.run(
                cmd, cwd=remotion_dir, check=True, shell=False,
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=600,
            )

        if not os.path.exists(final_video_path):
            print(f"[Remotion 렌더링 실패] 렌더 명령은 끝났지만 결과 파일이 없습니다: {final_video_path}")
            if result.stderr:
                print(f"  stderr: {result.stderr[:500]}")
            return None

        # 임시 props 파일 정리
        try:
            os.remove(props_json_path)
        except OSError:
            pass

        return final_video_path

    except subprocess.TimeoutExpired:
        print("[Remotion 렌더링 실패] 10분 타임아웃 초과. 렌더링이 너무 오래 걸립니다.")
        return None
    except subprocess.CalledProcessError as e:
        print(f"[Remotion 렌더링 실패] 종료 코드: {e.returncode}")
        if e.stdout:
            print(f"  stdout: {e.stdout[-500:]}")
        if e.stderr:
            print(f"  stderr: {e.stderr[-500:]}")
        return None
