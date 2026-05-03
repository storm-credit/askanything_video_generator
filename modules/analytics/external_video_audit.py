"""External YouTube Shorts visual audit.

This module samples public benchmark Shorts for local analysis only:
metadata -> short video sample -> first-second frames -> compact hook report.
It is meant to explain what successful external videos are doing visually,
without copying their scripts or redistributing their media.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat


ROOT = Path(__file__).resolve().parents[2]
AUDIT_DIR = ROOT / "assets" / "_external_benchmarks"
DEFAULT_FRAME_TIMES = (0.0, 0.5, 1.0, 2.0, 3.0)


def _int_env(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        value = int(os.getenv(name, str(default)).strip())
    except Exception:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _float_env(name: str, default: float, minimum: float | None = None, maximum: float | None = None) -> float:
    try:
        value = float(os.getenv(name, str(default)).strip())
    except Exception:
        value = default
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_frame_times(value: str | None = None) -> list[float]:
    raw = value if value is not None else os.getenv("EXTERNAL_VIDEO_AUDIT_FRAME_TIMES", "")
    if not raw.strip():
        return list(DEFAULT_FRAME_TIMES)
    times: list[float] = []
    for part in re.split(r"[,;\s]+", raw.strip()):
        if not part:
            continue
        try:
            times.append(round(max(0.0, float(part)), 2))
        except Exception:
            continue
    return times or list(DEFAULT_FRAME_TIMES)


def _parse_video_id(url: str) -> str | None:
    patterns = [
        r"shorts/([a-zA-Z0-9_-]{11})",
        r"[?&]v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"embed/([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url or "")
        if match:
            return match.group(1)
    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", url or ""):
        return url
    return None


def _youtube_url(video_id_or_url: str) -> str:
    video_id = _parse_video_id(video_id_or_url)
    if video_id:
        return f"https://www.youtube.com/shorts/{video_id}"
    return video_id_or_url


def _sanitize_stem(text: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z가-힣._-]+", "_", text or "").strip("._-")
    return safe[:120] or "video"


def _relative(path: Path | None) -> str | None:
    if not path:
        return None
    try:
        return str(path.resolve().relative_to(ROOT))
    except Exception:
        return str(path)


def _run_command(command: list[str], *, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _yt_dlp_command(*args: str) -> list[str]:
    return [sys.executable, "-m", "yt_dlp", *args]


def _format_section_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds - (hours * 3600) - (minutes * 60)
    if secs.is_integer():
        sec_text = f"{int(secs):02d}"
    else:
        sec_text = f"{secs:06.3f}".rstrip("0").rstrip(".")
    return f"{hours}:{minutes:02d}:{sec_text}"


def _assert_tooling() -> None:
    missing: list[str] = []
    if shutil.which("ffmpeg") is None:
        missing.append("ffmpeg")
    if shutil.which("ffprobe") is None:
        missing.append("ffprobe")
    yt_check = _run_command(_yt_dlp_command("--version"), timeout=20)
    if yt_check.returncode != 0:
        missing.append("yt-dlp")
    if missing:
        raise RuntimeError(f"Missing external video audit tools: {', '.join(missing)}")


def fetch_ytdlp_metadata(url: str) -> dict[str, Any]:
    """Fetch public metadata without downloading media."""
    result = _run_command(
        _yt_dlp_command("--dump-single-json", "--no-warnings", "--skip-download", url),
        timeout=_int_env("EXTERNAL_VIDEO_AUDIT_METADATA_TIMEOUT_SEC", 60, minimum=10),
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[:500]
        raise RuntimeError(f"yt-dlp metadata failed: {detail}")
    return json.loads(result.stdout)


def _audit_paths(video_id: str, market: str | None = None) -> dict[str, Path]:
    market_dir = _sanitize_stem((market or "GLOBAL").upper())
    base = AUDIT_DIR / market_dir / video_id
    return {
        "base": base,
        "frames": base / "frames",
        "sample": base / "sample.mp4",
        "contact_sheet": base / "contact_sheet.jpg",
        "report": AUDIT_DIR / "reports" / f"{video_id}.json",
    }


def download_video_sample(
    url: str,
    video_id: str,
    *,
    market: str | None = None,
    sample_seconds: float | None = None,
    max_duration_sec: int | None = None,
    force: bool = False,
) -> Path:
    """Download a short first-seconds sample for local analysis."""
    _assert_tooling()
    paths = _audit_paths(video_id, market)
    sample_path = paths["sample"]
    if sample_path.exists() and not force:
        return sample_path

    sample_path.parent.mkdir(parents=True, exist_ok=True)
    for stale in sample_path.parent.glob("sample.*"):
        try:
            stale.unlink()
        except OSError:
            pass

    sample_seconds = sample_seconds or _float_env("EXTERNAL_VIDEO_AUDIT_SAMPLE_SECONDS", 5.0, minimum=1.0, maximum=15.0)
    max_duration_sec = max_duration_sec or _int_env("EXTERNAL_VIDEO_AUDIT_MAX_DURATION_SEC", 120, minimum=10, maximum=600)
    output_template = str(sample_path.parent / "sample.%(ext)s")
    format_selector = os.getenv(
        "EXTERNAL_VIDEO_AUDIT_FORMAT",
        "bv*[ext=mp4][height<=720]+ba[ext=m4a]/b[ext=mp4][height<=720]/18/worst[ext=mp4]/worst",
    ).strip()

    command = _yt_dlp_command(
        "-f",
        format_selector,
        "--merge-output-format",
        "mp4",
        "--match-filter",
        f"duration<={max_duration_sec}",
        "--download-sections",
        f"*{_format_section_time(0)}-{_format_section_time(sample_seconds)}",
        "--force-keyframes-at-cuts",
        "-o",
        output_template,
        url,
    )
    result = _run_command(command, timeout=_int_env("EXTERNAL_VIDEO_AUDIT_DOWNLOAD_TIMEOUT_SEC", 180, minimum=30))
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()[:800]
        raise RuntimeError(f"yt-dlp sample download failed: {detail}")

    matches = sorted(sample_path.parent.glob("sample.*"))
    if not matches:
        raise RuntimeError("yt-dlp finished but no sample file was created")
    if sample_path.exists():
        return sample_path

    source = matches[0]
    ffmpeg = _run_command(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(sample_path),
        ],
        timeout=90,
    )
    if ffmpeg.returncode != 0 or not sample_path.exists():
        detail = (ffmpeg.stderr or ffmpeg.stdout or "").strip()[:500]
        raise RuntimeError(f"ffmpeg sample normalize failed: {detail}")
    return sample_path


def probe_video(video_path: Path) -> dict[str, Any]:
    result = _run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-print_format",
            "json",
            str(video_path),
        ],
        timeout=30,
    )
    if result.returncode != 0:
        return {}
    try:
        data = json.loads(result.stdout)
    except Exception:
        return {}
    video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
    return {
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "duration": float((data.get("format") or {}).get("duration") or 0),
        "avg_frame_rate": video_stream.get("avg_frame_rate"),
        "codec_name": video_stream.get("codec_name"),
    }


def extract_frames(
    video_path: Path,
    video_id: str,
    *,
    market: str | None = None,
    frame_times: list[float] | None = None,
    force: bool = False,
) -> list[Path]:
    paths = _audit_paths(video_id, market)
    frames_dir = paths["frames"]
    frames_dir.mkdir(parents=True, exist_ok=True)
    frame_times = frame_times or _parse_frame_times()

    frames: list[Path] = []
    for second in frame_times:
        frame_path = frames_dir / f"frame_{int(second * 1000):04d}ms.jpg"
        if frame_path.exists() and not force:
            frames.append(frame_path)
            continue
        result = _run_command(
            [
                "ffmpeg",
                "-y",
                "-loglevel",
                "error",
                "-ss",
                f"{second:.2f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-vf",
                "scale=720:-1",
                "-q:v",
                "2",
                str(frame_path),
            ],
            timeout=45,
        )
        if result.returncode == 0 and frame_path.exists() and frame_path.stat().st_size > 0:
            frames.append(frame_path)
    return frames


def _edge_density(image: Image.Image) -> dict[str, float]:
    gray = image.convert("L").resize((180, 320))
    edges = gray.filter(ImageFilter.FIND_EDGES)
    width, height = edges.size
    zones = {
        "top": (0, 0, width, int(height * 0.25)),
        "middle": (0, int(height * 0.25), width, int(height * 0.75)),
        "bottom": (0, int(height * 0.75), width, height),
    }
    result: dict[str, float] = {}
    for name, box in zones.items():
        crop = edges.crop(box)
        pixels = crop.getdata()
        result[name] = round(sum(1 for value in pixels if value > 40) / max(1, len(pixels)), 4)
    return result


def _caption_zone_signal(image: Image.Image) -> dict[str, dict[str, float | bool]]:
    gray = image.convert("L").resize((180, 320))
    width, height = gray.size
    zones = {
        "top": (0, 0, width, int(height * 0.28)),
        "middle": (0, int(height * 0.28), width, int(height * 0.72)),
        "bottom": (0, int(height * 0.72), width, height),
    }
    result: dict[str, dict[str, float | bool]] = {}
    for name, box in zones.items():
        crop = gray.crop(box)
        pixels = list(crop.getdata())
        bright_ratio = sum(1 for value in pixels if value >= 210) / max(1, len(pixels))
        dark_ratio = sum(1 for value in pixels if value <= 55) / max(1, len(pixels))
        mid_ratio = sum(1 for value in pixels if 70 <= value <= 190) / max(1, len(pixels))
        signal = bright_ratio >= 0.0035 and dark_ratio >= 0.12 and mid_ratio <= 0.74
        result[name] = {
            "bright_ratio": round(bright_ratio, 4),
            "dark_ratio": round(dark_ratio, 4),
            "signal": signal,
        }
    return result


def _image_metrics(path: Path) -> dict[str, Any]:
    with Image.open(path) as raw:
        image = raw.convert("RGB")
        width, height = image.size
        stat = ImageStat.Stat(image)
        brightness = sum(stat.mean) / 3
        contrast = sum(stat.stddev) / 3
        hsv = image.convert("HSV")
        saturation = ImageStat.Stat(hsv).mean[1]
        return {
            "path": _relative(path),
            "width": width,
            "height": height,
            "brightness": round(brightness, 1),
            "contrast": round(contrast, 1),
            "saturation": round(saturation, 1),
            "edge_density": _edge_density(image),
            "caption_zones": _caption_zone_signal(image),
        }


def _motion_score(frame_paths: list[Path]) -> dict[str, Any]:
    scores: list[float] = []
    previous: Image.Image | None = None
    for path in frame_paths:
        with Image.open(path) as raw:
            current = raw.convert("L").resize((96, 170))
            if previous is not None:
                diff = ImageStat.Stat(ImageChops.difference(previous, current)).mean[0]
                scores.append(round(diff, 1))
            previous = current.copy()
    avg = round(sum(scores) / max(1, len(scores)), 1)
    return {
        "avg_frame_delta": avg,
        "frame_deltas": scores,
        "pace": "fast" if avg >= 36 else "medium" if avg >= 16 else "slow",
    }


def summarize_visual_metrics(frame_paths: list[Path]) -> dict[str, Any]:
    frame_metrics = [_image_metrics(path) for path in frame_paths]
    motion = _motion_score(frame_paths) if len(frame_paths) >= 2 else {
        "avg_frame_delta": 0,
        "frame_deltas": [],
        "pace": "unknown",
    }
    edge_rows = [m["edge_density"] for m in frame_metrics]
    caption_rows = [m["caption_zones"] for m in frame_metrics]
    top_edge = sum(row["top"] for row in edge_rows) / max(1, len(edge_rows))
    bottom_edge = sum(row["bottom"] for row in edge_rows) / max(1, len(edge_rows))
    middle_edge = sum(row["middle"] for row in edge_rows) / max(1, len(edge_rows))
    caption_signal = any(
        bool(zone.get("signal"))
        for row in caption_rows
        for zone in row.values()
    )
    text_overlay_candidate = top_edge >= 0.11 or bottom_edge >= 0.11 or middle_edge >= 0.16 or caption_signal

    tags: list[str] = []
    if frame_metrics and frame_metrics[0]["height"] > frame_metrics[0]["width"]:
        tags.append("vertical_9_16")
    if text_overlay_candidate:
        tags.append("text_overlay_candidate")
    if motion["pace"] == "fast":
        tags.append("fast_opening_motion")
    elif motion["pace"] == "slow":
        tags.append("static_or_explainer_opening")

    avg_brightness = round(
        sum(m["brightness"] for m in frame_metrics) / max(1, len(frame_metrics)),
        1,
    )
    if avg_brightness < 70:
        tags.append("dark_opening")
    elif avg_brightness > 185:
        tags.append("bright_opening")

    return {
        "frames": frame_metrics,
        "motion": motion,
        "avg_brightness": avg_brightness,
        "text_overlay_candidate": text_overlay_candidate,
        "edge_density_avg": {
            "top": round(top_edge, 4),
            "middle": round(middle_edge, 4),
            "bottom": round(bottom_edge, 4),
        },
        "caption_signal": caption_signal,
        "tags": tags,
    }


def make_contact_sheet(frame_paths: list[Path], output_path: Path, *, title: str = "") -> Path | None:
    if not frame_paths:
        return None
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cell_w, cell_h = 216, 384
    label_h = 34
    margin = 10
    columns = min(len(frame_paths), 5)
    rows = (len(frame_paths) + columns - 1) // columns
    sheet_w = columns * cell_w + (columns + 1) * margin
    title_h = 42 if title else 0
    sheet_h = title_h + rows * (cell_h + label_h) + (rows + 1) * margin
    sheet = Image.new("RGB", (sheet_w, sheet_h), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    font = _contact_sheet_font(15)
    label_font = _contact_sheet_font(12)

    if title:
        draw.text((margin, 12), title[:90], fill=(235, 235, 235), font=font)

    for index, frame_path in enumerate(frame_paths):
        row = index // columns
        col = index % columns
        x = margin + col * (cell_w + margin)
        y = title_h + margin + row * (cell_h + label_h)
        with Image.open(frame_path) as raw:
            image = raw.convert("RGB")
            fitted = ImageOps.contain(image, (cell_w, cell_h))
            canvas = Image.new("RGB", (cell_w, cell_h), (0, 0, 0))
            paste_x = (cell_w - fitted.width) // 2
            paste_y = (cell_h - fitted.height) // 2
            canvas.paste(fitted, (paste_x, paste_y))
        sheet.paste(canvas, (x, y))
        label = frame_path.stem.replace("frame_", "").replace("ms", " ms")
        draw.text((x, y + cell_h + 8), label, fill=(230, 230, 230), font=label_font)

    sheet.save(output_path, quality=92)
    return output_path


def _contact_sheet_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/malgun.ttf"),
        Path("C:/Windows/Fonts/arial.ttf"),
    ]
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except Exception:
                continue
    return ImageFont.load_default()


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    try:
        data = json.loads(cleaned)
    except Exception:
        return {"raw": (text or "").strip()[:1200]}
    return data if isinstance(data, dict) else {"raw": (text or "").strip()[:1200]}


def analyze_contact_sheet_with_gemini(
    contact_sheet: Path,
    *,
    title: str = "",
    transcript_hook: str = "",
    locale: str | None = None,
) -> dict[str, Any]:
    """Analyze sampled frames with Gemini if credentials are available."""
    from google.genai import types

    from modules.utils.gemini_client import create_gemini_client
    from modules.utils.keys import get_google_key

    api_key = get_google_key(None, service="gemini") or os.getenv("GEMINI_API_KEY")
    if not api_key and os.getenv("GEMINI_BACKEND", "ai_studio").lower().strip() != "vertex_ai":
        return {"skipped": True, "reason": "no Gemini key"}

    client = create_gemini_client(api_key=api_key)
    prompt = f"""
You are analyzing the first seconds of an external YouTube Shorts benchmark.
Do not copy the creator's script. Extract reusable patterns only.

Title: {title}
Transcript hook if available: {transcript_hook}
Locale: {locale or "unknown"}

Return compact JSON only:
{{
  "visual_hook": "what the opening screen makes the viewer feel/ask",
  "first_second": "what appears to happen in the first second",
  "screen_pattern_tags": ["big_caption", "face", "object_closeup", "animation", "stock_clip", "fast_zoom", "comparison", "mystery"],
  "on_screen_text_guess": "short guess, if visible",
  "hook_mechanism": "curiosity_gap / scale_shock / danger / impossible_question / cute_or_gross / other",
  "adaptation_directive": "how our channels should adapt this without copying"
}}
""".strip()
    response = client.models.generate_content(
        model=os.getenv("EXTERNAL_VIDEO_AUDIT_VISION_MODEL", "gemini-2.5-flash"),
        contents=[
            types.Part.from_bytes(
                data=contact_sheet.read_bytes(),
                mime_type="image/jpeg",
            ),
            prompt,
        ],
    )
    return _extract_json_object(getattr(response, "text", "") or "")


def _extract_signal_url(row: dict[str, Any]) -> str | None:
    notes = row.get("notes")
    if not notes:
        return None
    try:
        data = json.loads(notes)
    except Exception:
        return None
    url = str(data.get("url") or "").strip()
    return url or None


def _simple_structure(transcript: str) -> dict[str, Any]:
    if not transcript:
        return {
            "hook": "",
            "ending": "",
            "sentence_count": 0,
            "estimated_duration_sec": 0,
        }
    sentences = re.split(r"[.!?。？！]\s*", transcript)
    sentences = [sentence.strip() for sentence in sentences if sentence.strip()]
    hook = sentences[0] if sentences else transcript[:120]
    ending = sentences[-1] if sentences else ""
    return {
        "hook": hook[:140],
        "ending": ending[:140],
        "sentence_count": len(sentences),
        "estimated_duration_sec": round(len(transcript) / 5, 1),
    }


def _guess_transcript_language(text: str) -> str:
    if re.search(r"[가-힣]", text or ""):
        return "ko"
    if re.search(r"[\u0900-\u097F]", text or ""):
        return "hi"
    if re.search(r"[¿¡áéíóúüñ]|\b(el|la|los|las|que|porque|datos|ciencia|luna)\b", (text or "").lower()):
        return "es"
    if re.search(r"[A-Za-z]", text or ""):
        return "en"
    return "unknown"


def _load_transcript_hook(video_id: str, locale: str | None = None) -> tuple[str, dict[str, Any]]:
    """Load public YouTube captions only. Paid ASR/video APIs stay opt-in via vision."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        api = YouTubeTranscriptApi()
        preferred = [lang for lang in [locale, "en", "es", "ko", "hi"] if lang]
        seen: set[str] = set()
        languages = [lang for lang in preferred if not (lang in seen or seen.add(lang))]
        transcript = ""
        source_language = ""
        try:
            entries = api.fetch(video_id, languages=languages)
            transcript = " ".join(s.text for s in entries if s.text)
            source_language = getattr(entries, "language_code", "") or ""
        except Exception:
            try:
                transcript_list = api.list(video_id)
                for item in transcript_list:
                    if getattr(item, "language_code", "") in languages:
                        entries = item.fetch()
                        transcript = " ".join(s.text for s in entries if s.text)
                        source_language = getattr(item, "language_code", "") or ""
                        if transcript:
                            break
                if not transcript:
                    for item in transcript_list:
                        entries = item.fetch()
                        transcript = " ".join(s.text for s in entries if s.text)
                        source_language = getattr(item, "language_code", "") or ""
                        if transcript:
                            break
            except Exception:
                transcript = ""
        structure = _simple_structure(transcript)
        detected_language = source_language or _guess_transcript_language(transcript)
        structure["transcript_language"] = detected_language
        structure["transcript_source"] = "youtube_captions" if transcript else "none"
        structure["locale_mismatch"] = bool(locale and detected_language not in {"unknown", locale})
        return transcript[:1200], structure
    except Exception as exc:
        return "", {"error": str(exc)}


def _save_report(report: dict[str, Any], report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def audit_external_video(
    url: str,
    *,
    market: str | None = None,
    locale: str | None = None,
    source_signal_id: int | None = None,
    force: bool = False,
    vision: bool | None = None,
    keep_video: bool = False,
) -> dict[str, Any]:
    """Run visual/hook audit for one external Shorts URL."""
    resolved_url = _youtube_url(url)
    video_id = _parse_video_id(resolved_url)
    if not video_id:
        return {"success": False, "error": "invalid YouTube URL", "url": url}

    paths = _audit_paths(video_id, market)
    if paths["report"].exists() and not force:
        try:
            return json.loads(paths["report"].read_text(encoding="utf-8"))
        except Exception:
            pass

    metadata = fetch_ytdlp_metadata(resolved_url)
    title = str(metadata.get("title") or "")
    sample = download_video_sample(
        resolved_url,
        video_id,
        market=market,
        force=force,
    )
    frame_paths = extract_frames(
        sample,
        video_id,
        market=market,
        frame_times=_parse_frame_times(),
        force=force,
    )
    contact_sheet = make_contact_sheet(frame_paths, paths["contact_sheet"], title=title)
    transcript, structure = _load_transcript_hook(video_id, locale=locale)
    metrics = summarize_visual_metrics(frame_paths)
    probe = probe_video(sample)

    should_use_vision = _truthy(os.getenv("EXTERNAL_VIDEO_AUDIT_USE_VISION"), default=False) if vision is None else vision
    vision_report: dict[str, Any] | None = None
    if should_use_vision and contact_sheet:
        try:
            vision_report = analyze_contact_sheet_with_gemini(
                contact_sheet,
                title=title,
                transcript_hook=structure.get("hook") or transcript[:180],
                locale=locale,
            )
        except Exception as exc:
            vision_report = {"error": str(exc)}

    if not keep_video:
        try:
            sample.unlink(missing_ok=True)
        except OSError:
            pass

    report = {
        "success": True,
        "video_id": video_id,
        "url": resolved_url,
        "market": (market or "").upper() or None,
        "locale": locale,
        "source_signal_id": source_signal_id,
        "title": title,
        "channel": metadata.get("channel") or metadata.get("uploader"),
        "view_count": metadata.get("view_count"),
        "like_count": metadata.get("like_count"),
        "duration": metadata.get("duration"),
        "fetched_at": datetime.now().isoformat(),
        "probe": probe,
        "sample_path": _relative(sample) if keep_video and sample.exists() else None,
        "frames": [_relative(path) for path in frame_paths],
        "contact_sheet": _relative(contact_sheet) if contact_sheet else None,
        "transcript_hook": structure.get("hook") or "",
        "structure": structure,
        "visual_metrics": metrics,
        "vision": vision_report,
    }
    _save_report(report, paths["report"])
    return report


def audit_benchmark_videos(
    *,
    market: str | None = None,
    locale: str | None = None,
    limit: int = 3,
    min_views: int | None = None,
    force: bool = False,
    vision: bool | None = None,
    keep_video: bool = False,
) -> dict[str, Any]:
    """Audit top cached external benchmark rows that have YouTube URLs."""
    from modules.utils.global_topic_signals import list_signals

    rows = list_signals(
        market=market,
        locale=locale,
        limit=max(limit * 3, limit),
        min_views=min_views,
    )
    selected: list[dict[str, Any]] = []
    for row in rows:
        url = _extract_signal_url(row)
        if not url:
            continue
        selected.append(row)
        if len(selected) >= limit:
            break

    reports: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for row in selected:
        url = _extract_signal_url(row)
        if not url:
            continue
        try:
            reports.append(
                audit_external_video(
                    url,
                    market=row.get("market") or market,
                    locale=row.get("locale") or locale,
                    source_signal_id=int(row.get("id") or 0) or None,
                    force=force,
                    vision=vision,
                    keep_video=keep_video,
                )
            )
        except Exception as exc:
            errors.append({
                "signal_id": row.get("id"),
                "title": row.get("title"),
                "url": url,
                "error": str(exc),
            })

    return {
        "success": bool(reports),
        "market": market,
        "locale": locale,
        "requested_limit": limit,
        "audited": len(reports),
        "errors": errors,
        "reports": reports,
    }


def list_audit_reports(limit: int = 50) -> list[dict[str, Any]]:
    report_dir = AUDIT_DIR / "reports"
    if not report_dir.exists():
        return []
    reports: list[dict[str, Any]] = []
    for path in sorted(report_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        reports.append({
            "video_id": data.get("video_id"),
            "title": data.get("title"),
            "market": data.get("market"),
            "channel": data.get("channel"),
            "view_count": data.get("view_count"),
            "fetched_at": data.get("fetched_at"),
            "contact_sheet": data.get("contact_sheet"),
            "visual_tags": (data.get("visual_metrics") or {}).get("tags", []),
            "vision": data.get("vision"),
            "report_path": _relative(path),
        })
        if len(reports) >= limit:
            break
    return reports


def _main() -> int:
    parser = argparse.ArgumentParser(description="Audit external YouTube Shorts visual hooks.")
    parser.add_argument("--url", help="YouTube Shorts/watch URL or video id")
    parser.add_argument("--market", help="Benchmark market, e.g. US, MX, KR, US_HISPANIC")
    parser.add_argument("--locale", help="Locale/language hint, e.g. en, es, ko")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--min-views", type=int)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--vision", action="store_true", help="Use Gemini vision on the contact sheet")
    parser.add_argument("--keep-video", action="store_true", help="Keep downloaded sample clips")
    args = parser.parse_args()

    if args.url:
        result = audit_external_video(
            args.url,
            market=args.market,
            locale=args.locale,
            force=args.force,
            vision=args.vision,
            keep_video=args.keep_video,
        )
    else:
        result = audit_benchmark_videos(
            market=args.market,
            locale=args.locale,
            limit=args.limit,
            min_views=args.min_views,
            force=args.force,
            vision=args.vision,
            keep_video=args.keep_video,
        )
    sys.stdout.buffer.write(json.dumps(result, indent=2, ensure_ascii=False).encode("utf-8", errors="replace"))
    sys.stdout.buffer.write(b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
