import os
import re
import json
import math
import shutil
import subprocess
import tempfile
from datetime import datetime

from modules.transcription.whisper import build_fallback_word_timestamps
from modules.utils.audio import probe_audio_duration

# 브랜드 이미지 (brand/ → assets/로 자동 복사하여 Remotion에서 접근)
BRAND_DIR = "brand"
INTRO_IMAGE = "intro.png"
OUTRO_IMAGE = "outro.jpg"
BGM_FILE = "bgm.mp3"
INTRO_DURATION_FRAMES = 24         # 1초 @ 24fps
OUTRO_DURATION_FRAMES = 24         # 1초 @ 24fps

# 채널별 브랜드 에셋 지원
# brand/channels/askanything/intro.png, outro.jpg
# brand/channels/wonderdrop/intro.png, outro.jpg
CHANNELS_DIR = os.path.join(BRAND_DIR, "channels")


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


def _select_bgm(bgm_theme: str = "random", channel: str | None = None) -> str | None:
    """채널별 BGM 우선 → brand/bgm/ 테마별 → brand/bgm.mp3 폴백."""
    import random

    if bgm_theme == "none":
        return None

    # 1) 채널 전용 BGM 우선: brand/channels/{channel}/bgm.mp3
    if channel:
        channel_bgm = os.path.join(BRAND_DIR, "channels", channel, BGM_FILE)
        if os.path.exists(channel_bgm):
            print(f"  [BGM] 채널 전용 배경음악: {channel}/{BGM_FILE}")
            return channel_bgm

    # 2) 테마별 BGM: brand/bgm/epic.mp3, brand/bgm/calm.mp3 등
    bgm_dir = os.path.join(BRAND_DIR, "bgm")
    single_bgm = os.path.join(BRAND_DIR, BGM_FILE)

    if os.path.isdir(bgm_dir):
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

    # 3) 단일 파일 폴백: brand/bgm.mp3
    return single_bgm if os.path.exists(single_bgm) else None


def _prepare_public_dir(
    visual_paths: list[str],
    audio_paths: list[str],
    intro_src: str | None,
    outro_src: str | None,
    bgm_src: str | None,
) -> tuple[str, dict[str, str]]:
    """렌더에 필요한 파일만 ASCII 이름으로 복사한 최소 public dir 생성.

    Returns:
        (pub_dir, path_map) — path_map: 원본 절대경로 → pub_dir 내 상대 경로
    """
    pub_dir = tempfile.mkdtemp(prefix="remotion_pub_")
    path_map: dict[str, str] = {}

    def _link(src: str, rel_name: str) -> str:
        dst = os.path.join(pub_dir, rel_name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        abs_src = os.path.abspath(src)
        try:
            os.link(abs_src, dst)
        except OSError:
            print(f"[Remotion] hardlink 실패, 복사로 전환: {os.path.basename(abs_src)}")
            try:
                shutil.copy2(abs_src, dst)
            except Exception as e:
                raise FileNotFoundError(f"Remotion public dir 준비 실패: {abs_src} → {dst}: {e}")
        path_map[abs_src] = rel_name
        return rel_name

    for i, (v, a) in enumerate(zip(visual_paths, audio_paths)):
        ext_v = os.path.splitext(v)[1]
        ext_a = os.path.splitext(a)[1]
        _link(v, f"v{i:02d}{ext_v}")
        _link(a, f"a{i:02d}{ext_a}")

    if intro_src:
        _link(intro_src, "intro" + os.path.splitext(intro_src)[1])

    if outro_src:
        _link(outro_src, "outro" + os.path.splitext(outro_src)[1])

    if bgm_src:
        _link(bgm_src, "bgm" + os.path.splitext(bgm_src)[1])

    return pub_dir, path_map


def _render_single(props_data: dict, props_json_path: str, video_path: str, remotion_dir: str, pub_dir: str, label: str = "") -> str | None:
    """단일 Remotion 렌더 실행. 성공 시 video_path 반환."""
    with open(props_json_path, "w", encoding="utf-8") as f:
        json.dump(props_data, f, ensure_ascii=False, indent=2)

    abs_video_path = os.path.abspath(video_path)
    abs_props_path = os.path.abspath(props_json_path)

    # CPU 코어 수에 맞춰 병렬 렌더링 (최소 2, 최대 os.cpu_count)
    concurrency = max(2, min(os.cpu_count() or 4, 8))

    cmd = [
        "npx", "remotion", "render", "src/index.ts", "Main",
        abs_video_path, "--props", abs_props_path, "--public-dir", pub_dir,
        "--concurrency", str(concurrency),
    ]

    total_frames = props_data.get("totalDurationInFrames", 0)
    print(f"-> [Remotion 렌더링{label}] 총 길이 {total_frames} 프레임, 렌더링 시작...")

    try:
        if os.name == "nt":
            # .cmd 파일 우회: node로 직접 remotion-cli.js 실행 (콘솔 창 방지)
            node_exe = shutil.which("node") or "node"
            remotion_cli_js = os.path.join(
                remotion_dir, "node_modules", "@remotion", "cli", "remotion-cli.js"
            )
            if os.path.exists(remotion_cli_js):
                cmd = [node_exe, remotion_cli_js] + cmd[2:]  # npx remotion → node + cli.js
            else:
                cmd[0] = shutil.which("npx") or "npx.cmd"
            import subprocess as _sp
            result = subprocess.run(
                cmd, cwd=remotion_dir, check=True, shell=False,
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=600,
                creationflags=_sp.CREATE_NO_WINDOW,
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
# 쇼츠(30-60초)에서 인트로/아웃트로는 시청 이탈 유발 → 의도적 비활성
PLATFORM_CONFIGS = {
    "youtube": {"intro": False, "outro": False, "title": True},
    "tiktok":  {"intro": False, "outro": False, "title": True},
    "reels":   {"intro": False, "outro": False, "title": True},
}


def _extract_emotion(description: str) -> str | None:
    """description에서 [SHOCK], [WONDER] 등 감정 태그를 추출합니다."""
    match = re.search(r'\[(SHOCK|WONDER|TENSION|REVEAL|URGENCY|DISBELIEF|IDENTITY|CALM|LOOP)\]', description or "", re.IGNORECASE)
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
    fps = 24
    desc_list = descriptions or [""] * len(visual_paths)

    # 브랜드 에셋 준비 (채널별 원본 경로 직접 사용 — 공유 assets/ 덮어쓰기 방지)
    channel_label = f" ({channel})" if channel else ""
    intro_src = _resolve_brand_asset(INTRO_IMAGE, channel)
    outro_src = _resolve_brand_asset(OUTRO_IMAGE, channel)
    intro_available = intro_src is not None and os.path.exists(intro_src)
    outro_available = outro_src is not None and os.path.exists(outro_src)

    # BGM 준비 — 채널별 원본 경로 직접 사용 (공유 assets/bgm.mp3 거치지 않음)
    bgm_source = _select_bgm(bgm_theme, channel=channel)
    bgm_src_path = None
    if bgm_source and os.path.exists(bgm_source):
        bgm_src_path = os.path.abspath(bgm_source)
        print(f"-> [BGM] 배경음악 '{os.path.basename(bgm_source)}' ({channel or 'default'}) 전체 영상에 적용")

    # Remotion 환경 검증
    remotion_dir = os.path.abspath("remotion")
    if not os.path.exists(os.path.join(remotion_dir, "node_modules")):
        print("[Remotion 렌더링 실패] remotion/node_modules가 없습니다. `npm --prefix remotion install` 실행 필요")
        return None

    # topic_folder는 "assets/폴더명" 또는 "폴더명" 형태 허용
    # 유니코드(한글) + 콤마/괄호 등 특수문자 포함 폴더도 허용 (경로 이탈만 차단)
    folder_name = os.path.basename(topic_folder) if '/' in topic_folder or '\\' in topic_folder else topic_folder
    if not folder_name or '..' in folder_name:
        print(f"[Remotion 보안 오류] topic_folder가 비어 있거나 경로 이탈 시도: {folder_name}")
        return None

    camera = camera_style if camera_style in ("auto", "dynamic", "gentle", "static", "cinematic") else "dynamic"

    # 최소 public dir 생성 (필요한 파일만 ASCII 이름으로)
    pub_dir, path_map = _prepare_public_dir(
        visual_paths, audio_paths,
        intro_src if intro_available else None,
        outro_src if outro_available else None,
        bgm_src_path,
    )

    try:
        # path_map을 역방향으로 사용하여 props에 pub_dir 상대 경로 설정
        cuts_data = []
        cuts_duration = 0

        for idx, (visual_path, audio_path, _script, word_timestamps) in enumerate(zip(
            visual_paths, audio_paths, scripts, word_timestamps_list
        )):
            DEFAULT_CUT_SEC = 5.0
            MIN_CUT_SEC = 2.0
            TAIL_PADDING = 0.7
            TIMESTAMP_GAP_TOLERANCE = 0.35
            audio_duration_sec = probe_audio_duration(audio_path)
            effective_timestamps = word_timestamps or []

            if audio_duration_sec > 0:
                covered_until = float(effective_timestamps[-1].get("end", 0.0)) if effective_timestamps else 0.0
                needs_fallback = (
                    not effective_timestamps
                    or covered_until + TIMESTAMP_GAP_TOLERANCE < audio_duration_sec
                )
                if needs_fallback and _script:
                    fallback = build_fallback_word_timestamps(_script, audio_duration_sec)
                    if fallback:
                        effective_timestamps = fallback

            if effective_timestamps:
                covered_until = float(effective_timestamps[-1].get("end", 0.0))
                duration_anchor = max(covered_until, audio_duration_sec)
                duration_sec = max(MIN_CUT_SEC, duration_anchor + TAIL_PADDING)
            elif audio_duration_sec > 0:
                duration_sec = max(MIN_CUT_SEC, audio_duration_sec + TAIL_PADDING)
            else:
                duration_sec = DEFAULT_CUT_SEC

            frames = max(math.ceil(duration_sec * fps), fps)
            cuts_duration += frames

            abs_visual = os.path.abspath(visual_path)
            abs_audio = os.path.abspath(audio_path)
            cut_entry: dict = {
                "visual_path": path_map.get(abs_visual, visual_path),
                "audio_path": path_map.get(abs_audio, audio_path),
                "word_timestamps": effective_timestamps,
                "duration_in_frames": frames,
            }

            emotion = _extract_emotion(desc_list[idx] if idx < len(desc_list) else "")
            if emotion:
                cut_entry["emotion"] = emotion

            cuts_data.append(cut_entry)

        # 플랫폼 결정
        if not platforms:
            platforms = ["youtube"]

        valid_platforms = [p for p in platforms if p in PLATFORM_CONFIGS]
        if not valid_platforms:
            valid_platforms = ["youtube"]

        multi = len(valid_platforms) > 1
        if multi:
            print(f"-> [멀티 플랫폼] {', '.join(p.upper() for p in valid_platforms)} 버전 생성 (API 토큰 추가 비용 없음)")

        results: dict[str, str] = {}

        # 플랫폼별 설정이 동일하면 1번만 렌더하고 나머지는 복사
        rendered_configs: dict[str, str] = {}  # config_key → rendered video path

        for platform in valid_platforms:
            cfg = PLATFORM_CONFIGS[platform]
            label = f" {platform.upper()}" if multi else ""

            # pub_dir 내 상대 경로 참조
            intro_rel = path_map.get(os.path.abspath(intro_src)) if (cfg["intro"] and intro_available) else None
            outro_rel = path_map.get(os.path.abspath(outro_src)) if (cfg["outro"] and outro_available) else None
            bgm_rel = path_map.get(os.path.abspath(bgm_src_path)) if bgm_src_path else None
            use_title = title if cfg["title"] else None

            # 설정 키: 동일 설정이면 렌더링 재사용
            config_key = f"{intro_rel}|{outro_rel}|{use_title}"

            suffix = f"_{platform}" if multi else ""
            video_path = os.path.join(output_dir, f"{topic_folder}_{timestamp}{suffix}.mp4")

            if config_key in rendered_configs:
                # 동일 설정 → 복사로 대체 (렌더링 스킵)
                shutil.copy2(rendered_configs[config_key], video_path)
                results[platform] = video_path
                print(f"-> [완료{label}] 동일 설정 — 복사 완료")
                continue

            total_frames = cuts_duration
            if intro_rel:
                total_frames += INTRO_DURATION_FRAMES
                print(f"-> [인트로{label}] 브랜드 인트로{channel_label} 추가")
            if outro_rel:
                total_frames += OUTRO_DURATION_FRAMES
                print(f"-> [아웃트로{label}] 브랜드 아웃트로{channel_label} 추가")
            if use_title:
                print(f"-> [제목{label}] '{use_title}' — 첫 컷 위 오버레이")

            props_data = {
                "cuts": cuts_data,
                "totalDurationInFrames": total_frames,
                "introImagePath": intro_rel,
                "outroImagePath": outro_rel,
                "bgmPath": bgm_rel,
                "title": use_title,
                "cameraStyle": camera,
                "captionSize": caption_size,
                "captionY": caption_y,
                "channel": channel,
            }

            props_path = os.path.join(output_dir, f"remotion_props{suffix}.json")

            result = _render_single(props_data, props_path, video_path, remotion_dir, pub_dir, label)
            if result:
                results[platform] = result
                rendered_configs[config_key] = result
                print(f"-> [완료{label}] {result}")

    except Exception as e:
        import traceback
        print(f"[Remotion 치명적 오류] {e}")
        traceback.print_exc()
        return None
    finally:
        # 임시 public dir 정리
        try:
            shutil.rmtree(pub_dir, ignore_errors=True)
        except Exception:
            pass

    if not results:
        print(f"[Remotion] 모든 플랫폼 렌더 실패. valid_platforms={valid_platforms}")
        return None

    # 단일 플랫폼이면 기존 호환성 유지 (str 반환)
    if len(valid_platforms) == 1:
        return next(iter(results.values()))

    return results
