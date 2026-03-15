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


def _select_bgm(bgm_theme: str = "random") -> str | None:
    """brand/bgm/ 폴더에서 테마별 BGM 선택. 단일 brand/bgm.mp3도 호환."""
    import random
    bgm_dir = os.path.join(BRAND_DIR, "bgm")
    single_bgm = os.path.join(BRAND_DIR, BGM_FILE)

    if bgm_theme == "none":
        return None

    if os.path.isdir(bgm_dir):
        # 테마별 파일: brand/bgm/epic.mp3, brand/bgm/calm.mp3 등
        available = {}
        for f in os.listdir(bgm_dir):
            if f.lower().endswith(('.mp3', '.wav', '.m4a')):
                theme_name = os.path.splitext(f)[0].lower()
                available[theme_name] = os.path.join(bgm_dir, f)

        if not available:
            return single_bgm if os.path.exists(single_bgm) else None

        if bgm_theme == "random":
            chosen = random.choice(list(available.values()))
        elif bgm_theme in available:
            chosen = available[bgm_theme]
        else:
            chosen = random.choice(list(available.values()))
            print(f"  [BGM] 테마 '{bgm_theme}' 없음 → 랜덤 선택")

        return chosen

    # brand/bgm/ 폴더 없으면 단일 파일 폴백
    return single_bgm if os.path.exists(single_bgm) else None


def create_remotion_video(visual_paths: list[str], audio_paths: list[str], scripts: list[str], word_timestamps_list: list[list[dict]], topic_folder: str, title: str = "", camera_style: str = "dynamic", bgm_theme: str = "random") -> str | None:
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
        # 적응형 컷 타이밍: Whisper 오디오 끝 기준 + 시각적 여유 패딩
        # 참고: 숏폼 편집 이론 — 컷당 0.3~0.5초 tail padding이 자연스러운 호흡감 제공
        DEFAULT_CUT_SEC = 5.0
        MIN_CUT_SEC = 2.0  # 최소 2초 (너무 짧으면 시각적으로 불안정)
        TAIL_PADDING = 0.4  # 대사 끝 후 시각적 여유
        if word_timestamps:
            audio_end = word_timestamps[-1].get("end", 0)
            duration_sec = max(MIN_CUT_SEC, audio_end + TAIL_PADDING)
        else:
            duration_sec = DEFAULT_CUT_SEC

        frames = max(int(duration_sec * fps), fps)  # 최소 1초(24프레임) 보장
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

    # 브랜드 에셋 복사 (변경된 경우만)
    for asset_name in [INTRO_IMAGE, OUTRO_IMAGE]:
        brand_src = os.path.join(BRAND_DIR, asset_name)
        assets_dst = os.path.join("assets", asset_name)
        if os.path.exists(brand_src):
            # 이미 동일한 파일이면 복사 건너뜀
            if not os.path.exists(assets_dst) or os.path.getmtime(brand_src) > os.path.getmtime(assets_dst):
                shutil.copy2(brand_src, assets_dst)

    if os.path.exists(os.path.join("assets", INTRO_IMAGE)):
        intro_image_path = INTRO_IMAGE
        total_duration_in_frames += INTRO_DURATION_FRAMES
        print(f"-> [인트로] 브랜드 인트로 {INTRO_DURATION_FRAMES}프레임 (1초) 추가")

    if title:
        print(f"-> [제목] '{title}' — 첫 컷 위 오버레이로 표시")

    if os.path.exists(os.path.join("assets", OUTRO_IMAGE)):
        outro_image_path = OUTRO_IMAGE
        total_duration_in_frames += OUTRO_DURATION_FRAMES
        print(f"-> [아웃트로] 브랜드 아웃트로 {OUTRO_DURATION_FRAMES}프레임 (1초) 추가")

    # BGM: 테마별 선택 (중복 복사 방지)
    bgm_path = None
    bgm_source = _select_bgm(bgm_theme)
    if bgm_source and os.path.exists(bgm_source):
        bgm_dest = os.path.join("assets", BGM_FILE)
        if not os.path.exists(bgm_dest) or os.path.getmtime(bgm_source) > os.path.getmtime(bgm_dest):
            shutil.copy2(bgm_source, bgm_dest)
        bgm_path = BGM_FILE
        bgm_name = os.path.basename(bgm_source)
        print(f"-> [BGM] 배경음악 '{bgm_name}' 전체 영상에 적용")

    props_data = {
        "cuts": cuts_data,
        "totalDurationInFrames": total_duration_in_frames,
        "introImagePath": intro_image_path,
        "outroImagePath": outro_image_path,
        "bgmPath": bgm_path,
        "title": title or None,
        "cameraStyle": camera_style if camera_style in ("dynamic", "gentle", "static") else "dynamic",
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
