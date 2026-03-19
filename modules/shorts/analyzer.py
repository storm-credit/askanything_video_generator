"""YouTube Shorts 스타일 분석 모듈.

쇼츠 URL → yt-dlp 오디오 추출 → Whisper 전사 → LLM 패턴 분석.
분석 결과는 generate_cuts()의 style_ref로 주입되어 동일 패턴의 새 영상을 생성합니다.
"""

import os
import re
import json
import tempfile
import subprocess
from typing import Any


# YouTube Shorts URL 패턴 (youtube.com/shorts/, youtu.be/, youtube.com/watch)
_SHORTS_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:"
    r"youtube\.com/shorts/[\w\-]+"
    r"|youtu\.be/[\w\-]+"
    r"|youtube\.com/watch\?v=[\w\-]+"
    r")",
    re.IGNORECASE,
)


def is_shorts_url(text: str) -> bool:
    """입력 텍스트가 YouTube 쇼츠/영상 URL인지 판별."""
    return bool(_SHORTS_URL_RE.match(text.strip()))


def _extract_audio(url: str, output_dir: str) -> str:
    """yt-dlp로 오디오만 추출 (mp3). 반환: 오디오 파일 경로."""
    output_path = os.path.join(output_dir, "shorts_audio.%(ext)s")
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "5",  # 중간 품질 (속도 우선)
        "--max-filesize", "25m",  # Whisper API 제한
        "--output", output_path,
        "--no-warnings",
        "--quiet",
        url,
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            stderr = result.stderr[:500] if result.stderr else "알 수 없는 오류"
            raise RuntimeError(f"yt-dlp 실패 (코드 {result.returncode}): {stderr}")
    except FileNotFoundError:
        raise RuntimeError(
            "yt-dlp가 설치되어 있지 않습니다. `pip install yt-dlp` 또는 `brew install yt-dlp`로 설치하세요."
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("yt-dlp 다운로드 시간 초과 (60초)")

    # 실제 생성된 파일 찾기
    for f in os.listdir(output_dir):
        if f.startswith("shorts_audio") and f.endswith(".mp3"):
            return os.path.join(output_dir, f)

    raise RuntimeError("yt-dlp 오디오 추출 성공했으나 출력 파일을 찾을 수 없습니다.")


def _extract_metadata(url: str) -> dict[str, Any]:
    """yt-dlp로 영상 메타데이터 추출 (제목, 길이, 채널명)."""
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--dump-json",
        "--no-warnings",
        "--quiet",
        url,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout)
        return {
            "title": data.get("title", ""),
            "duration": data.get("duration", 0),
            "channel": data.get("channel", ""),
            "view_count": data.get("view_count", 0),
            "description": data.get("description", "")[:300],
        }
    except Exception:
        return {}


def _transcribe(audio_path: str, api_key: str | None = None) -> str:
    """Whisper API로 전사. 전체 텍스트 반환."""
    from openai import OpenAI

    key = api_key or os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Whisper 전사에 OPENAI_API_KEY가 필요합니다.")

    client = OpenAI(api_key=key)

    with open(audio_path, "rb") as f:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="text",
        )

    return transcript.strip() if isinstance(transcript, str) else str(transcript).strip()


def _analyze_pattern(transcript: str, metadata: dict, llm_provider: str = "gemini",
                     llm_key: str | None = None) -> dict[str, Any]:
    """LLM으로 쇼츠 스크립트 패턴을 분석합니다.

    반환:
        {
            "hook_style": "질문형 / 결론선행형 / 충격수치형 / ...",
            "structure": ["hook", "fact1", "twist", "climax", "cta"],
            "tone": "casual, shock-value, ...",
            "pacing": "fast / medium / slow",
            "cut_count": 8,
            "techniques": ["반전", "비유", "숫자 활용", ...],
            "summary": "한 줄 요약",
        }
    """
    # 분석 프롬프트는 아래 연구/프레임워크에 기반:
    # - Attention Economy (Herbert Simon): 첫 2초 hook이 시청 유지율 결정
    # - Zeigarnik Effect: 미완결 정보(cliffhanger)가 댓글/공유 유도
    # - Aristotle's Rhetoric (Ethos/Pathos/Logos): 설득 기법 분류
    # - YouTube Creator Academy: Hook→Build→Payoff 3단 구조
    # - TikTok viral research (Stokel-Walker 2022): 평균 8.25초 attention span
    system_prompt = """You are a viral content analyst specializing in YouTube Shorts and TikTok.
Your task is to reverse-engineer the exact storytelling pattern from a transcript.

[ANALYSIS FRAMEWORK — Based on Attention Economy & Narrative Psychology Research]

1. HOOK STYLE (첫 2초 — 시청 유지율의 70% 결정, Herbert Simon's Attention Economy)
   Categories:
   - conclusion_first (결론선행): 답을 먼저 제시. "블랙홀에 빠지면 몸이 늘어난다"
   - question (질문형): 호기심 갭 활용 (Loewenstein's Information Gap Theory). "이거 왜 그런지 알아?"
   - shocking_number (충격수치): 구체적 숫자로 인지 부조화 유발. "99%가 모르는"
   - impossible_claim (불가능 주장): 상식 파괴. "사실 태양은 노란색이 아니야"
   - direct_address (직접호명): 2인칭 개입. "너 이거 하고 있으면 당장 멈춰"
   - controversy (논쟁유발): 의도적 양극화. "과학자들도 인정 못하는 사실"
   - pattern_interrupt (패턴차단): 예상 깨기. 무관한 이미지+충격 텍스트

2. NARRATIVE STRUCTURE — 각 문장의 서사적 역할 (Freytag's Pyramid 변형)
   hook → context → fact → shock_chain → twist → climax → callback → cta → cliffhanger

3. TONE — 감정 곡선 (Plutchik's Wheel of Emotions 기반)
   casual/formal × funny/serious × educational/entertainment
   감정 전이: 어떤 감정에서 시작해서 어떤 감정으로 끝나는가?

4. PACING — 정보 밀도 (Sentences per 10 seconds)
   fast(>3): 팩트 폭격형, medium(2-3): 스토리텔링형, slow(<2): 감성/시각 중심

5. RHETORICAL TECHNIQUES (Aristotle + 현대 설득 심리학)
   - analogy (비유): 추상 → 구체. "지구가 농구공이면 태양은 아파트"
   - numbers (숫자 활용): 구체적 수치로 신뢰도 상승
   - reversal (반전): 기대 전복으로 도파민 분비 유발
   - repetition (반복): 핵심 키워드 반복으로 기억 강화
   - escalation (에스컬레이션): 충격 강도를 점진적으로 높임
   - social_proof (사회적 증거): "과학자들에 의하면", "NASA 발표"
   - scarcity (희소성): "거의 아무도 모르는", "숨겨진 진실"
   - contrast (대비): Before/After, 크기 비교 등
   - callback (콜백): 앞에서 언급한 내용을 마지막에 재소환

6. CTA STYLE — 행동 유도 (Zeigarnik Effect 활용)
   comment_bait, follow_bait, cliffhanger, emotional_close, challenge

[OUTPUT FORMAT]
Return ONLY this JSON:
{
  "hook_style": "category_name",
  "hook_example": "exact first sentence from transcript",
  "structure": ["hook", "fact", "shock_chain", ...],
  "tone": "description",
  "emotion_arc": "curiosity → shock → awe",
  "pacing": "fast|medium|slow",
  "cut_count": number,
  "techniques": ["technique1", "technique2"],
  "cta_style": "style",
  "summary": "one-line pattern summary in Korean"
}"""

    meta_info = ""
    if metadata:
        meta_info = f"\n\n[Video Metadata]\nTitle: {metadata.get('title', 'N/A')}\nDuration: {metadata.get('duration', 'N/A')}s\nViews: {metadata.get('view_count', 'N/A')}"

    user_content = f"Analyze this YouTube Shorts transcript and extract the storytelling pattern:{meta_info}\n\n[TRANSCRIPT]\n{transcript}"

    from modules.gpt.cutter import _extract_json

    if llm_provider == "gemini":
        # analyzer 전용: cutter의 schema-bound _request_gemini 대신 직접 호출
        import google.genai as genai
        from modules.utils.keys import get_google_key
        key = llm_key or get_google_key(None, service="gemini")
        if not key:
            raise RuntimeError("Gemini API 키가 없습니다.")
        client = genai.Client(api_key=key)
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        resp = client.models.generate_content(
            model=model,
            contents=[{"role": "user", "parts": [{"text": user_content}]}],
            config={"system_instruction": system_prompt, "response_mime_type": "application/json"},
        )
        raw = resp.text
    elif llm_provider == "claude":
        from modules.gpt.cutter import _request_claude
        key = llm_key or os.getenv("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("Claude API 키가 없습니다.")
        raw = _request_claude(key, system_prompt, user_content)
    else:
        from modules.gpt.cutter import _request_openai_freeform
        key = llm_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OpenAI API 키가 없습니다.")
        raw = _request_openai_freeform(key, system_prompt, user_content)

    try:
        return _extract_json(raw)
    except (json.JSONDecodeError, ValueError):
        # JSON 파싱 실패 시 기본 구조 반환
        return {
            "hook_style": "unknown",
            "structure": ["hook", "fact", "climax", "cta"],
            "tone": "casual",
            "pacing": "fast",
            "cut_count": 8,
            "techniques": [],
            "summary": "패턴 분석 실패 — 기본 구조 적용",
            "_raw": raw[:500],
        }


def analyze_shorts(url: str, llm_provider: str = "gemini",
                   llm_key: str | None = None,
                   openai_key: str | None = None) -> dict[str, Any]:
    """전체 분석 파이프라인: URL → 오디오 → 전사 → 패턴 분석.

    Returns:
        {
            "url": str,
            "metadata": { title, duration, channel, view_count },
            "transcript": str,
            "pattern": { hook_style, structure, tone, ... },
        }
    """
    print(f"-> [쇼츠 분석] URL 분석 시작: {url}")

    # 1. 메타데이터 추출 (빠름, 실패해도 계속)
    print("-> [쇼츠 분석] 메타데이터 추출 중...")
    metadata = _extract_metadata(url)
    if metadata:
        print(f"   제목: {metadata.get('title', 'N/A')} ({metadata.get('duration', '?')}초)")

    # 2. 오디오 추출
    print("-> [쇼츠 분석] 오디오 다운로드 중 (yt-dlp)...")
    tmp_dir = tempfile.mkdtemp(prefix="shorts_analyze_")
    try:
        audio_path = _extract_audio(url, tmp_dir)
        print(f"   오디오 크기: {os.path.getsize(audio_path) / 1024:.0f}KB")

        # 3. Whisper 전사
        print("-> [쇼츠 분석] Whisper 전사 중...")
        transcript = _transcribe(audio_path, openai_key)
        if not transcript:
            raise RuntimeError("Whisper 전사 결과가 비어 있습니다.")
        print(f"   전사 완료: {len(transcript)}자")

    finally:
        # 임시 파일 정리
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)

    # 4. LLM 패턴 분석
    print(f"-> [쇼츠 분석] {llm_provider.upper()} 패턴 분석 중...")
    pattern = _analyze_pattern(transcript, metadata, llm_provider, llm_key)
    print(f"OK [쇼츠 분석] 패턴: {pattern.get('hook_style', '?')} / {pattern.get('pacing', '?')} / {len(pattern.get('techniques', []))}개 기법")

    return {
        "url": url,
        "metadata": metadata,
        "transcript": transcript,
        "pattern": pattern,
    }


def build_style_ref_prompt(pattern: dict[str, Any]) -> str:
    """분석된 패턴을 generate_cuts system prompt에 주입할 문자열로 변환.

    이 프롬프트는 Few-shot 없이 패턴 명세만으로 LLM의 출력을 제어합니다.
    연구 근거: Instruction Following > Few-shot (Wei et al. 2022, "Finetuned Language Models are Zero-Shot Learners")
    """
    if not pattern:
        return ""

    hook_style = pattern.get("hook_style", "unknown")
    structure = pattern.get("structure", [])
    tone = pattern.get("tone", "casual")
    pacing = pattern.get("pacing", "fast")
    techniques = pattern.get("techniques", [])
    cta_style = pattern.get("cta_style", "")
    hook_example = pattern.get("hook_example", "")
    emotion_arc = pattern.get("emotion_arc", "")

    parts = [
        "",
        "[STYLE REFERENCE — Clone from analyzed viral Shorts]",
        "You MUST replicate this exact storytelling pattern. This pattern was extracted from a high-view-count Shorts.",
        "",
        f"1. HOOK (Cut 1): Use '{hook_style}' hook style.",
    ]

    if hook_example:
        parts.append(f"   Reference: \"{hook_example}\"")
        parts.append(f"   → Adapt this EXACT format to the new topic. Keep the sentence structure, change the content.")

    if structure:
        parts.append(f"2. NARRATIVE ARC: {' → '.join(structure)}")
        parts.append(f"   Each cut must fulfill its assigned role in this sequence. Do NOT rearrange.")

    parts.append(f"3. TONE: {tone}")

    if emotion_arc:
        parts.append(f"4. EMOTION ARC: {emotion_arc}")
        parts.append(f"   The viewer's emotional journey must follow this curve.")

    parts.append(f"5. PACING: {pacing}")
    pacing_guide = {
        "fast": "High information density. Every sentence drops a new fact or shock.",
        "medium": "Balanced storytelling. Facts interwoven with build-up.",
        "slow": "Cinematic, atmospheric. Let visuals breathe.",
    }
    parts.append(f"   → {pacing_guide.get(pacing, pacing_guide['fast'])}")

    if techniques:
        parts.append(f"6. RHETORICAL TECHNIQUES (MUST USE ALL):")
        for t in techniques:
            parts.append(f"   - {t}")

    if cta_style:
        parts.append(f"7. ENDING: Use '{cta_style}' style for the final cut.")

    parts.extend([
        "",
        "CRITICAL CONSTRAINTS:",
        f"- The hook MUST use '{hook_style}' style — this is non-negotiable.",
        f"- Use at least {max(len(techniques), 2)} rhetorical techniques from the list above.",
        f"- The narrative structure MUST follow the exact sequence: {' → '.join(structure) if structure else 'hook → fact → climax → cta'}.",
        "- Do NOT deviate from the analyzed pattern. You are CLONING a proven viral format.",
    ])

    return "\n".join(parts)
