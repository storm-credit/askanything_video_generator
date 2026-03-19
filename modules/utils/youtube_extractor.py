"""YouTube Shorts/영상 분석 → 레퍼런스 컨텍스트 추출 모듈"""

import os
import re
import threading
import time

_ref_cache: dict[str, tuple[float, dict]] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 3600  # 1시간


def _parse_video_id(url: str) -> str | None:
    """YouTube URL에서 video_id를 추출한다. shorts/watch/youtu.be 모두 지원."""
    patterns = [
        r"shorts/([a-zA-Z0-9_-]{11})",
        r"[?&]v=([a-zA-Z0-9_-]{11})",
        r"youtu\.be/([a-zA-Z0-9_-]{11})",
        r"embed/([a-zA-Z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _fetch_metadata(video_id: str, api_key: str) -> dict:
    """YouTube Data API v3로 영상 메타데이터를 가져온다."""
    try:
        from googleapiclient.discovery import build
        youtube = build("youtube", "v3", developerKey=api_key)
        resp = youtube.videos().list(
            part="snippet,statistics",
            id=video_id,
        ).execute()

        items = resp.get("items", [])
        if not items:
            return {}

        snippet = items[0].get("snippet", {})
        stats = items[0].get("statistics", {})
        return {
            "title": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "channel": snippet.get("channelTitle", ""),
            "tags": snippet.get("tags", []),
            "view_count": int(stats.get("viewCount", 0)),
            "like_count": int(stats.get("likeCount", 0)),
        }
    except Exception as e:
        print(f"[YouTube 분석] Data API 실패, yt-dlp fallback 시도: {e}")
        return _fetch_metadata_ytdlp(video_id)


def _fetch_metadata_ytdlp(video_id: str) -> dict:
    """yt-dlp로 메타데이터를 가져온다 (API 키 불필요, JS 런타임 불필요)."""
    try:
        import subprocess
        url = f"https://www.youtube.com/watch?v={video_id}"
        # --print 방식: --dump-json과 달리 JS 런타임 불필요
        # Unit Separator(\x1f)로 구분 — 제목에 탭 문자가 포함될 수 있으므로
        _SEP = "\x1f"
        result = subprocess.run(
            ["python", "-m", "yt_dlp", "--no-download",
             "--print", f"%(title)s{_SEP}%(uploader)s{_SEP}%(view_count)s{_SEP}%(like_count)s{_SEP}%(description).200s",
             url],
            capture_output=True, text=True, timeout=30, encoding="utf-8",
        )
        if result.returncode != 0 or not result.stdout.strip():
            return {}
        parts = result.stdout.strip().split(_SEP)
        if len(parts) < 2:
            return {}
        return {
            "title": parts[0] if parts[0] != "NA" else "",
            "description": parts[4] if len(parts) > 4 and parts[4] != "NA" else "",
            "channel": parts[1] if parts[1] != "NA" else "",
            "tags": [],
            "view_count": int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0,
            "like_count": int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0,
        }
    except Exception as e:
        print(f"[YouTube 분석] yt-dlp fallback도 실패: {e}")
        return {}


def _fetch_transcript(video_id: str) -> str:
    """자막 추출: youtube-transcript-api → Whisper → Gemini 영상 분석."""
    # 1단계: youtube-transcript-api로 자막 시도
    text = _fetch_transcript_api(video_id)
    if text:
        return text

    # 2단계: Whisper 오디오 전사
    print(f"  [YouTube 분석] 자막 없음 → Whisper 오디오 전사 시도...")
    text = _fetch_transcript_whisper(video_id)
    if text and len(text) > 20:  # "MÚSICA" 같은 짧은 결과 제외
        print(f"  [YouTube 분석] Whisper 전사 완료! ({len(text)}자)")
        return text

    # 3단계: 음성 없는 영상 → Gemini 멀티모달로 영상 내용 분석
    print(f"  [YouTube 분석] 음성 없음 → Gemini 영상 분석 시도...")
    text = _analyze_video_gemini(video_id)
    if text:
        print(f"  [YouTube 분석] Gemini 영상 분석 완료! ({len(text)}자)")
    return text


def _fetch_transcript_api(video_id: str) -> str:
    """youtube-transcript-api로 자막 추출. 한국어 → 영어 → 주요 언어 순."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        api = YouTubeTranscriptApi()

        for lang in ["ko", "en"]:
            try:
                entries = api.fetch(video_id, languages=[lang])
                lines = [s.text for s in entries if s.text]
                if lines:
                    return " ".join(lines)
            except Exception:
                continue

        _USEFUL_LANGS = {"ko", "en", "ja", "zh", "es", "fr", "de", "pt", "hi", "id", "vi", "th", "ru", "ar"}
        try:
            transcript_list = api.list(video_id)
            for t in transcript_list:
                if not t.is_generated:
                    try:
                        entries = t.fetch()
                        lines = [s.text for s in entries if s.text]
                        if lines:
                            return " ".join(lines)
                    except Exception:
                        continue
            for t in transcript_list:
                if t.is_generated and hasattr(t, 'language_code') and t.language_code in _USEFUL_LANGS:
                    try:
                        entries = t.fetch()
                        lines = [s.text for s in entries if s.text]
                        if lines:
                            return " ".join(lines)
                    except Exception:
                        continue
        except Exception:
            pass
        return ""
    except Exception:
        return ""


def _fetch_transcript_whisper(video_id: str) -> str:
    """yt-dlp로 오디오 다운로드 → OpenAI Whisper API로 전사."""
    import subprocess
    import tempfile
    try:
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            return ""

        url = f"https://www.youtube.com/watch?v={video_id}"
        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = os.path.join(tmpdir, "audio.m4a")
            # yt-dlp로 오디오만 다운로드 (최소 품질, 60초 제한)
            result = subprocess.run(
                ["python", "-m", "yt_dlp",
                 "-x", "--audio-format", "m4a",
                 "--audio-quality", "9",  # 최저 품질 (전사에 충분)
                 "--match-filter", "duration<120",  # 2분 이하만
                 "-o", audio_path,
                 url],
                capture_output=True, text=True, timeout=60, encoding="utf-8",
            )
            if result.returncode != 0 or not os.path.exists(audio_path):
                # m4a 실패 시 다른 확장자 시도
                import glob
                files = glob.glob(os.path.join(tmpdir, "audio.*"))
                if files:
                    audio_path = files[0]
                else:
                    return ""

            # Whisper API로 전사
            from openai import OpenAI
            client = OpenAI(api_key=openai_key, timeout=60)
            with open(audio_path, "rb") as f:
                transcript = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=f,
                    response_format="text",
                )
            return (transcript or "").strip()
    except Exception as e:
        print(f"  [YouTube 분석] Whisper 전사 실패: {e}")
        return ""


def _analyze_video_gemini(video_id: str) -> str:
    """yt-dlp로 영상 다운로드 → Gemini 멀티모달로 내용 분석."""
    import subprocess
    import tempfile
    try:
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            return ""

        url = f"https://www.youtube.com/watch?v={video_id}"
        with tempfile.TemporaryDirectory() as tmpdir:
            video_path = os.path.join(tmpdir, "video.mp4")
            # 최저 품질 영상 다운로드 (분석용)
            result = subprocess.run(
                ["python", "-m", "yt_dlp",
                 "-f", "worst[ext=mp4]/worst",
                 "--match-filter", "duration<120",
                 "-o", video_path,
                 url],
                capture_output=True, text=True, timeout=60, encoding="utf-8",
            )
            if result.returncode != 0:
                return ""
            # 파일 확인
            import glob
            files = glob.glob(os.path.join(tmpdir, "video.*"))
            if not files:
                return ""
            video_path = files[0]

            # Gemini에 영상 업로드 + 분석
            import google.genai as genai
            from modules.utils.keys import get_google_key
            key = get_google_key(None, service="gemini") or gemini_key
            client = genai.Client(api_key=key)

            # 파일 업로드 + 처리 대기
            uploaded = client.files.upload(file=video_path)
            # Gemini 파일 처리 대기 (ACTIVE 상태까지)
            for _ in range(30):  # 최대 60초
                status = client.files.get(name=uploaded.name)
                if status.state.name == "ACTIVE":
                    break
                time.sleep(2)
            else:
                print(f"  [YouTube 분석] Gemini 파일 처리 타임아웃")
                return ""

            # 영상 분석 요청
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    uploaded,
                    "이 YouTube 쇼츠 영상의 내용을 상세히 분석해주세요. "
                    "1) 영상에서 보이는 장면, 텍스트, 효과를 순서대로 설명 "
                    "2) 영상의 핵심 주제/메시지 "
                    "3) 사용된 시각적 기법 (텍스트 오버레이, 트랜지션, 이미지 등) "
                    "한국어로 답변. 300자 이내."
                ],
            )
            text = (response.text or "").strip()

            # 업로드 파일 삭제
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                pass

            return text
    except Exception as e:
        print(f"  [YouTube 분석] Gemini 영상 분석 실패: {e}")
        return ""


def _analyze_structure(transcript: str) -> dict:
    """자막 텍스트에서 쇼츠 구조를 간단히 분석한다."""
    if not transcript:
        return {"hook": "", "style": "unknown", "sentence_count": 0}

    sentences = re.split(r"[.!?。？！]\s*", transcript)
    sentences = [s.strip() for s in sentences if s.strip()]

    hook = sentences[0] if sentences else ""
    ending = sentences[-1] if sentences else ""

    # 말투 감지
    casual_markers = ["거든", "잖아", "걸?", "ㄹㅇ", "미쳤", "대박", "진짜"]
    formal_markers = ["입니다", "합니다", "습니다", "습니까"]

    casual_count = sum(1 for s in sentences for m in casual_markers if m in s)
    formal_count = sum(1 for s in sentences for m in formal_markers if m in s)
    if casual_count == 0 and formal_count == 0:
        style = "unknown"
    else:
        style = "casual" if casual_count >= formal_count else "formal"

    # 결론 패턴
    question_ending = ending.endswith("?") or any(m in ending for m in ["걸?", "잖아?", "거든?"])

    return {
        "hook": hook[:100],
        "ending": ending[:100],
        "style": style,
        "sentence_count": len(sentences),
        "has_question_ending": question_ending,
        "estimated_duration_sec": len(transcript) / 5,  # rough estimate
    }


def extract_youtube_reference(url: str, api_key: str | None = None) -> dict:
    """
    YouTube URL → 레퍼런스 분석 결과를 반환한다.

    Returns:
        {
            "video_id": str,
            "title": str,
            "channel": str,
            "view_count": int,
            "transcript": str,
            "structure": { hook, ending, style, sentence_count, ... },
            "context_string": str  # LLM에 주입할 포맷팅된 문자열
        }
    """
    video_id = _parse_video_id(url)
    if not video_id:
        print(f"[YouTube 분석] 유효한 YouTube URL이 아닙니다: {url}")
        return {}

    # 캐시 확인
    cache_key = video_id
    with _cache_lock:
        cached = _ref_cache.get(cache_key)
        if cached and time.time() - cached[0] < _CACHE_TTL:
            return cached[1]

    # API 키 결정
    key = api_key or os.getenv("GEMINI_API_KEY")

    print(f"-> [레퍼런스 분석] YouTube 영상 '{video_id}' 분석 중...")

    # 메타데이터 + 자막 병렬이면 좋지만, 간단하게 순차
    # API 키 없어도 yt-dlp fallback이 있으므로 항상 시도
    metadata = _fetch_metadata(video_id, key)
    transcript = _fetch_transcript(video_id)
    structure = _analyze_structure(transcript)

    result = {
        "video_id": video_id,
        "title": metadata.get("title", ""),
        "channel": metadata.get("channel", ""),
        "description": metadata.get("description", ""),
        "tags": metadata.get("tags", []),
        "view_count": metadata.get("view_count", 0),
        "like_count": metadata.get("like_count", 0),
        "transcript": transcript,
        "structure": structure,
    }

    print(f"OK [레퍼런스 분석] 완료! 제목: {result['title']}, 자막 {len(transcript)}자 추출")

    # 캐시 저장 (50개 초과 시 만료된 항목 정리)
    with _cache_lock:
        if len(_ref_cache) > 50:
            now = time.time()
            expired = [k for k, (ts, _) in _ref_cache.items() if now - ts > _CACHE_TTL]
            for k in expired:
                _ref_cache.pop(k, None)
        _ref_cache[cache_key] = (time.time(), result)

    return result
