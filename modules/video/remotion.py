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
INTRO_DURATION_FRAMES = 30         # 1초 @ 30fps
OUTRO_DURATION_FRAMES = 30         # 1초 @ 30fps

# 채널별 브랜드 에셋 지원
# brand/channels/askanything/intro.png, outro.jpg
# brand/channels/wonderdrop/intro.png, outro.jpg
CHANNELS_DIR = os.path.join(BRAND_DIR, "channels")


def _to_relative(p: str) -> str:
    """assets/ 기준 상대 경로 변환 (staticFile()용 - publicDir=assets/)"""
    normed = p.replace("\\", "/")
    idx = normed.find("assets/")
    return normed[idx + len("assets/"):] if idx >= 0 else normed


def _resolve_brand_asset(asset_name: str, channel: str | None = None) -> str | None:
    """채널별 브랜드 에셋 경로를 반환합니다.

    우선순위: brand/channels/{channel}/{asset} → brand/{asset} → None
    """
    if channel:
        channel_path = os.path.join(CHANNELS_DIR, channel, asset_name)
        if os.path.exists(channel_path):
            return channel_path

    default_path = os.path.join(BRAND_DIR, asset_name)
    if os.path.exists(default_path):
        return default_path

    return None


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


def _render_single(props_data: dict, props_json_path: str, video_path: str, remotion_dir: str, assets_dir: str, label: str = "") -> str | None:
    """단일 Remotion 렌더 실행. 성공 시 video_path 반환."""
    with open(props_json_path, "w", encoding="utf-8") as f:
        json.dump(props_data, f, ensure_ascii=False, indent=2)

    abs_video_path = os.path.abspath(video_path)
    abs_props_path = os.path.abspath(props_json_path)

    # CPU 코어 수에 맞춰 병렬 렌더링 (최소 2, 최대 os.cpu_count)
    concurrency = max(2, min(os.cpu_count() or 4, 8))

    cmd = [
        "npx", "remotion", "render", "src/index.ts", "Main",
        abs_video_path, "--props", abs_props_path, "--public-dir", assets_dir,
        "--concurrency", str(concurrency),
    ]

    total_frames = props_data.get("totalDurationInFrames", 0)
    print(f"-> [Remotion 렌더링{label}] 총 길이 {total_frames} 프레임, 렌더링 시작...")

    try:
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

        if not os.path.exists(video_path):
            print(f"[Remotion 렌더링 실패{label}] 결과 파일 없음: {video_path}")
            if result.stderr:
                print(f"  stderr: {result.stderr[:500]}")
            return None

        try:
            os.remove(props_json_path)
        except OSError:
            pass

        return video_path

    except subprocess.TimeoutExpired:
        print(f"[Remotion 렌더링 실패{label}] 10분 타임아웃 초과.")
        try:
            os.remove(props_json_path)
        except OSError:
            pass
        return None
    except subprocess.CalledProcessError as e:
        print(f"[Remotion 렌더링 실패{label}] 종료 코드: {e.returncode}")
        if e.stdout:
            print(f"  stdout: {e.stdout[-500:]}")
        if e.stderr:
            print(f"  stderr: {e.stderr[-500:]}")
        try:
            os.remove(props_json_path)
        except OSError:
            pass
        return None


# 플랫폼별 렌더링 설정
# youtube: 인트로 + 아웃트로 + 제목 오버레이 포함
# tiktok/reels: 인트로/아웃트로/제목 없이 본편만
PLATFORM_CONFIGS = {
    "youtube": {"intro": True, "outro": True, "title": True},
    "tiktok":  {"intro": False, "outro": False, "title": True},
    "reels":   {"intro": False, "outro": False, "title": True},
}


def _extract_emotion(description: str) -> str | None:
    """description에서 [SHOCK], [WONDER] 등 감정 태그를 추출합니다."""
    match = re.search(r'\[(SHOCK|WONDER|TENSION|REVEAL|CALM)\]', description or "", re.IGNORECASE)
    return match.group(1).upper() if match else None


def create_remotion_video(visual_paths: list[str], audio_paths: list[str], scripts: list[str], word_timestamps_list: list[list[dict]], topic_folder: str, title: str = "", camera_style: str = "dynamic", bgm_theme: str = "random", channel: str | None = None, platforms: list[str] | None = None, caption_size: int = 48, caption_y: int = 28, descriptions: list[str] | None = None) -> str | dict[str, str] | None:
    """
    Remotion 렌더링. platforms가 2개 이상이면 플랫폼별 영상을 각각 생성합니다.
    API 토큰 추가 비용 없이 로컬 렌더만 반복합니다.

    Returns:
        단일 플랫폼: str (video path)
        멀티 플랫폼: dict[platform, video_path]
        실패: None
    """
    try:
        _validate_inputs(visual_paths, audio_paths, scripts, word_timestamps_list)
    except Exception as e:
        print(f"[Remotion 입력 검증 실패] {e}")
        return None

    output_dir = os.path.join("assets", topic_folder, "video")
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 컷 데이터 공통 생성 (모든 플랫폼 공유)
    cuts_data = []
    cuts_duration = 0
    fps = 30

    desc_list = descriptions or [""] * len(visual_paths)

    for idx, (visual_path, audio_path, _script, word_timestamps) in enumerate(zip(
        visual_paths, audio_paths, scripts, word_timestamps_list
    )):
        DEFAULT_CUT_SEC = 5.0
        MIN_CUT_SEC = 2.0
        TAIL_PADDING = 0.4
        if word_timestamps:
            audio_end = word_timestamps[-1].get("end", 0)
            duration_sec = max(MIN_CUT_SEC, audio_end + TAIL_PADDING)
        else:
            duration_sec = DEFAULT_CUT_SEC

        frames = max(int(duration_sec * fps), fps)
        cuts_duration += frames

        cut_entry: dict = {
            "visual_path": _to_relative(visual_path),
            "audio_path": _to_relative(audio_path),
            "word_timestamps": word_timestamps or [],
            "duration_in_frames": frames,
        }

        emotion = _extract_emotion(desc_list[idx] if idx < len(desc_list) else "")
        if emotion:
            cut_entry["emotion"] = emotion

        cuts_data.append(cut_entry)

    # 브랜드 에셋 준비 (한 번만)
    channel_label = f" ({channel})" if channel else ""
    for asset_name in [INTRO_IMAGE, OUTRO_IMAGE]:
        brand_src = _resolve_brand_asset(asset_name, channel)
        assets_dst = os.path.join("assets", asset_name)
        if brand_src:
            if not os.path.exists(assets_dst) or os.path.getmtime(brand_src) > os.path.getmtime(assets_dst):
                shutil.copy2(brand_src, assets_dst)

    intro_available = os.path.exists(os.path.join("assets", INTRO_IMAGE))
    outro_available = os.path.exists(os.path.join("assets", OUTRO_IMAGE))

    # BGM 준비 (한 번만)
    bgm_path = None
    bgm_source = _select_bgm(bgm_theme)
    if bgm_source and os.path.exists(bgm_source):
        bgm_dest = os.path.join("assets", BGM_FILE)
        if not os.path.exists(bgm_dest) or os.path.getmtime(bgm_source) > os.path.getmtime(bgm_dest):
            shutil.copy2(bgm_source, bgm_dest)
        bgm_path = BGM_FILE
        print(f"-> [BGM] 배경음악 '{os.path.basename(bgm_source)}' 전체 영상에 적용")

    # Remotion 환경 검증
    remotion_dir = os.path.abspath("remotion")
    if not os.path.exists(os.path.join(remotion_dir, "node_modules")):
        print("[Remotion 렌더링 실패] remotion/node_modules가 없습니다. `npm --prefix remotion install` 실행 필요")
        return None

    if not re.match(r'^[\w\-]+$', topic_folder):
        print(f"[Remotion 보안 오류] topic_folder에 허용되지 않는 문자가 포함됨: {topic_folder}")
        return None

    assets_dir = os.path.abspath("assets")
    camera = camera_style if camera_style in ("auto", "dynamic", "gentle", "static") else "dynamic"

    # 플랫폼 결정: 기본 youtube만
    if not platforms:
        platforms = ["youtube"]

    valid_platforms = [p for p in platforms if p in PLATFORM_CONFIGS]
    if not valid_platforms:
        valid_platforms = ["youtube"]

    multi = len(valid_platforms) > 1
    if multi:
        print(f"-> [멀티 플랫폼] {', '.join(p.upper() for p in valid_platforms)} 버전 생성 (API 토큰 추가 비용 없음)")

    results: dict[str, str] = {}

    for platform in valid_platforms:
        cfg = PLATFORM_CONFIGS[platform]
        label = f" {platform.upper()}" if multi else ""

        # 플랫폼별 인트로/아웃트로/제목 설정
        intro_path = INTRO_IMAGE if (cfg["intro"] and intro_available) else None
        outro_path = OUTRO_IMAGE if (cfg["outro"] and outro_available) else None
        use_title = title if cfg["title"] else None

        total_frames = cuts_duration
        if intro_path:
            total_frames += INTRO_DURATION_FRAMES
            print(f"-> [인트로{label}] 브랜드 인트로{channel_label} 추가")
        if outro_path:
            total_frames += OUTRO_DURATION_FRAMES
            print(f"-> [아웃트로{label}] 브랜드 아웃트로{channel_label} 추가")
        if use_title:
            print(f"-> [제목{label}] '{use_title}' — 첫 컷 위 오버레이")

        props_data = {
            "cuts": cuts_data,
            "totalDurationInFrames": total_frames,
            "introImagePath": intro_path,
            "outroImagePath": outro_path,
            "bgmPath": bgm_path,
            "title": use_title,
            "cameraStyle": camera,
            "captionSize": caption_size,
            "captionY": caption_y,
        }

        suffix = f"_{platform}" if multi else ""
        video_path = os.path.join(output_dir, f"{topic_folder}_{timestamp}{suffix}.mp4")
        props_path = os.path.join(output_dir, f"remotion_props{suffix}.json")

        result = _render_single(props_data, props_path, video_path, remotion_dir, assets_dir, label)
        if result:
            results[platform] = result
            print(f"-> [완료{label}] {result}")

    if not results:
        return None

    # 단일 플랫폼이면 기존 호환성 유지 (str 반환)
    if len(valid_platforms) == 1:
        return next(iter(results.values()))

    return results
