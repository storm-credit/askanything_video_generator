import os
import json
import re
import time
import random
from typing import Any

from modules.utils.slugify import slugify_topic
from modules.utils.constants import PROVIDER_LABELS
from modules.gpt.search import get_fact_check_context

from .parser import _split_yt_topic, _sanitize_llm_input
from .llm_client import _request_cuts
from .verifier import _verify_subject_match, _verify_highness_structure, _verify_facts
from .quality import _validate_hard_fail, _validate_narrative_arc, _validate_region_style
from .enhancer import _enhance_image_prompts, _rewrite_academic_tone, polish_scripts, ensure_visual_prompts_in_english

_COUNTDOWN_CUE_PATTERN = re.compile(
    r"(?i)\btop\s*\d+\b|#\d+\b|\b(?:ranking|ranked|tier list|clasificación|랭킹|순위)\b"
)
_WHO_WINS_QUESTION_PATTERN = re.compile(
    r"(?i)\bwho(?:\s+\w+){0,2}\s+wins?\b|qui[eé]n\s+ganar[ií]a(?:\s+de\s+verdad)?\b|누가\s*(?:진짜\s*)?(?:이겨|더\s*강해)"
)


def _get_channel_hook_rules(channel: str | None, lang: str) -> str:
    """채널별 첫 컷 훅 스타일 규칙을 반환 — 생성 단계 주입용."""
    from modules.utils.channel_config import get_channel_hook_profile
    if channel:
        return f"[Channel Hook Style] {get_channel_hook_profile(channel)}"
    if lang == "ko":
        return "[Channel Hook Style] Cut 1 should be short, punchy, and immediately curiosity-inducing."
    if lang == "es":
        return "[Channel Hook Style] El corte 1 debe ser corto, claro e inmediatamente intrigante."
    return "[Channel Hook Style] Cut 1 should be short, clear, and immediately intriguing."


def _get_channel_title_rules(channel: str | None) -> str:
    """채널별 제목 공식을 반환."""
    from modules.utils.channel_config import get_channel_title_rule
    return f"[Channel Title Formula] {get_channel_title_rule(channel)}"


def _get_channel_cut1_scene_rules(channel: str | None) -> str:
    """채널별 컷1 비주얼 앵커 설명."""
    from modules.utils.channel_config import get_channel_cut1_visual_rule
    return f"[Channel Cut 1 Visual Anchor] {get_channel_cut1_visual_rule(channel)}"


def _should_run_fact_verify(topic_title: str, format_type: str | None, fact_context: str | None) -> bool:
    """팩트 검증 선택 실행 — 최신성/숫자/논쟁 리스크 큰 주제+포맷만 검증."""
    if not fact_context:
        return False
    fmt = (format_type or "").upper()
    # 고위험 포맷: 수치/논쟁/미스터리/과학 계열
    if fmt in {"FACT", "PARADOX", "MYSTERY", "COUNTDOWN", "EMOTIONAL_SCI"}:
        return True
    # 에버그린/비교형(WHO_WINS, SCALE, IF, EMOTIONAL_SCI): 주제에 위험 키워드 있을 때만
    title = (topic_title or "").lower()
    risk_keywords = [
        "study", "studies", "research", "scientists", "evidence",
        "연구", "논문", "과학자", "발견", "증거", "통계",
        "estudio", "cient", "evidencia", "descub",
    ]
    has_digits = re.search(r'\d{4}|\d+%', title) is not None
    return has_digits or any(k in title for k in risk_keywords)


def _ensure_format_metadata_tags(cuts: list[dict], format_type: str | None) -> None:
    """포맷 구조 태그가 description 메타데이터에서만 빠진 경우 보정."""
    if not cuts or not format_type:
        return

    fmt = format_type.upper()
    emotion_tag_pattern = re.compile(
        r"\[(SHOCK|WONDER|TENSION|REVEAL|URGENCY|DISBELIEF|IDENTITY|CALM|LOOP)\]",
        re.IGNORECASE,
    )

    def _set_cut_desc(cut: dict, desc: str) -> None:
        cut["description"] = desc
        cut["text"] = desc

    if fmt == "IF":
        expected_roles = {
            1: "SHOCK",
            2: "SETUP",
            3: "CHAIN_1",
            4: "CHAIN_2",
            5: "ESCALATE",
            6: "CHAIN_3",
            7: "BUILD",
            8: "PIVOT",
            9: "REVEAL",
        }
        for idx, role in expected_roles.items():
            cut_index = idx - 1
            if cut_index >= len(cuts):
                continue
            desc = cuts[cut_index].get("description", cuts[cut_index].get("text", "")) or ""
            if f"[{role}]" not in desc.upper():
                fixed = f"{desc.rstrip()} [{role}]".strip()
                _set_cut_desc(cuts[cut_index], fixed)

    if fmt == "EMOTIONAL_SCI":
        # 감성과학은 호기심/공감 기반 포맷이라 [SHOCK]가 hard fail이다.
        # 생성·rewrite 어느 단계에서 들어와도 게이트 직전에 안전 태그로 치환한다.
        for cut_index, cut in enumerate(cuts):
            desc = cut.get("description", cut.get("text", "")) or ""
            replacement = "[WONDER]" if cut_index == 0 else "[TENSION]"
            fixed = re.sub(r"\[SHOCK\]", replacement, desc, flags=re.IGNORECASE)
            if cut_index == 0 and not emotion_tag_pattern.search(fixed):
                fixed = f"{fixed.rstrip()} [WONDER]".strip()
            if fixed != desc:
                _set_cut_desc(cut, fixed)

    if fmt != "EMOTIONAL_SCI":
        last_desc = cuts[-1].get("description", cuts[-1].get("text", "")) or ""
        if "[LOOP]" not in last_desc.upper():
            fixed = f"{last_desc.rstrip()} [LOOP]".strip()
            _set_cut_desc(cuts[-1], fixed)


def _strip_countdown_cues(text: str) -> str:
    """TOP N/랭킹 신호를 일반 reveal 제목으로 정리한다."""
    if not text:
        return text

    cleaned = _COUNTDOWN_CUE_PATTERN.sub("", text)
    cleaned = re.sub(r"(?i)\bmost\b", "", cleaned)
    cleaned = re.sub(r"(?i)\bm[aá]s\b", "", cleaned)
    cleaned = re.sub(r"\s*[,/|-]\s*", ": ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+([:?!])", r"\1", cleaned)
    cleaned = re.sub(r":\s*:", ": ", cleaned)
    return cleaned.strip(" ,:-")


def _soften_who_wins_cues(text: str, lang: str) -> str:
    """직접 대결 신호를 비교/차이형 제목으로 약화한다."""
    if not text:
        return text

    connector = "와" if lang == "ko" else "y" if lang == "es" else "and"
    cleaned = re.sub(r"(?i)\s+\bvs\.?\b\s+", f" {connector} ", text)
    cleaned = re.sub(r"(?i)\s+\bversus\b\s+", f" {connector} ", cleaned)
    cleaned = _WHO_WINS_QUESTION_PATTERN.sub("", cleaned)
    cleaned = re.sub(r"\s*[,/|-]\s*", ": ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+([:?!])", r"\1", cleaned)
    cleaned = re.sub(r":\s*:", ": ", cleaned)
    return cleaned.strip(" ,:-?")


# 컷 자동 구성 함수 (천만 뷰 쇼츠 기획 전문가 - 멀티 LLM 지원)
def generate_cuts(topic: str, api_key_override: str = None, lang: str = "ko",
                  llm_provider: str = "gemini", llm_key_override: str = None,
                  channel: str | None = None, llm_model: str | None = None,
                  reference_url: str | None = None,
                  format_type: str | None = None,
                  *, _skip_verify: bool = False, _skip_visual_director: bool = False,
                  _skip_polish: bool = False) -> tuple[list[dict[str, Any]], str, str, list[str], str, str]:
    # YouTube 자막 포함된 topic에서 제목/자막 분리
    _topic_title, _topic_content = _split_yt_topic(topic)
    if not _topic_title:
        _topic_title = topic
    topic_folder = slugify_topic(_topic_title, lang)
    # 채널별 폴더 분리 (멀티채널 병렬 생성 시 파일 충돌 방지)
    if channel:
        topic_folder = f"{topic_folder}_{channel}"

    # 저장 폴더 구조 생성
    base_path = os.path.join("assets", topic_folder)
    os.makedirs(os.path.join(base_path, "images"), exist_ok=True)
    os.makedirs(os.path.join(base_path, "audio"), exist_ok=True)
    os.makedirs(os.path.join(base_path, "video"), exist_ok=True)

    requested_format = str(format_type or "").upper().strip() or None
    if not requested_format:
        try:
            from modules.gpt.prompts.formats import detect_format_type
            requested_format = detect_format_type(_topic_title, lang)
            if requested_format:
                print(f"-> [포맷 감지] {_topic_title} → {requested_format}")
        except Exception:
            requested_format = None

    if channel:
        from modules.utils.channel_config import normalize_format_for_channel
        normalized_format, format_guard_reason = normalize_format_for_channel(channel, requested_format)
    else:
        normalized_format, format_guard_reason = requested_format, None
    format_type = normalized_format

    if format_guard_reason:
        print(f"-> [포맷 가드] {format_guard_reason}")
    if requested_format == "COUNTDOWN" and format_type != "COUNTDOWN":
        normalized_topic = _strip_countdown_cues(_topic_title)
        if normalized_topic and normalized_topic != _topic_title:
            print(f"-> [토픽 가드] COUNTDOWN 신호 제거 → {normalized_topic}")
            _topic_title = normalized_topic
    if requested_format == "WHO_WINS" and format_type != "WHO_WINS":
        normalized_topic = _soften_who_wins_cues(_topic_title, lang)
        if normalized_topic and normalized_topic != _topic_title:
            print(f"-> [토픽 가드] WHO_WINS 신호 완화 → {normalized_topic}")
            _topic_title = normalized_topic

    # System Prompt — 외부 파일에서 로드 (modules/gpt/prompts/)
    from modules.gpt.prompts import load_system_prompt, inject_channel_config, inject_format_prompt
    system_prompt = load_system_prompt(lang, channel)
    system_prompt = inject_channel_config(system_prompt, channel)
    if format_type:
        system_prompt = inject_format_prompt(system_prompt, format_type, lang)
        print(f"-> [포맷 주입] {format_type} ({lang})")

    # ── 이하 원본 인라인 프롬프트 (외부 파일로 이동됨) ──
    # 파일 위치: modules/gpt/prompts/system_{ko,en,es_us,es_latam}.txt
    # 채널 설정 주입: modules/gpt/prompts/__init__.py:inject_channel_config()

    # LLM 프로바이더별 API 키 결정
    provider_label = PROVIDER_LABELS.get(llm_provider, "ChatGPT")

    if llm_provider == "gemini":
        final_api_key = llm_key_override or os.getenv("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEYS", "").split(",")[0].strip()
        # Vertex AI 서비스 계정 모드에서는 API 키 없이도 동작
        if not final_api_key and os.getenv("GEMINI_BACKEND", "ai_studio") != "vertex_ai":
            raise EnvironmentError("Gemini API 키가 제공되지 않았습니다. .env에 GEMINI_API_KEY를 설정하세요.")
    elif llm_provider == "claude":
        final_api_key = llm_key_override or os.getenv("ANTHROPIC_API_KEY")
        if not final_api_key:
            raise EnvironmentError("Claude API 키가 제공되지 않았습니다. .env에 ANTHROPIC_API_KEY를 설정하세요.")
    else:
        from modules.utils.provider_policy import get_openai_api_key, is_openai_api_disabled
        final_api_key = get_openai_api_key(api_key_override)
        if not final_api_key:
            if is_openai_api_disabled():
                raise EnvironmentError("OpenAI API가 비활성화되어 GPT 기획을 실행하지 않습니다.")
            raise EnvironmentError("OpenAI API 키가 제공되지 않았습니다. .env에 OPENAI_API_KEY를 설정하세요.")

    print(f"-> [기획 전문가] {provider_label} 기반 스크립트 및 기획안 작성 중...")

    # RAG 기법: 실시간 검색 팩트체크 주입 (제목만 사용)
    fact_context = get_fact_check_context(_topic_title)
    # 외부 입력 새니타이징 (프롬프트 인젝션 방어)
    _safe_title = _sanitize_llm_input(_topic_title, max_len=200)
    _safe_content = _sanitize_llm_input(_topic_content, max_len=1500) if _topic_content else ""
    if lang == "en":
        user_content = f"Topic: Create a short-form video plan about '{_safe_title}'."
    elif lang == "es":
        user_content = f"Tema: Crea un plan de video corto sobre '{_safe_title}'."
    else:
        user_content = f"주제: '{_safe_title}'에 대한 숏폼 기획안을 작성해주세요."
    # YouTube 원본 자막이 있으면 LLM 컨텍스트로 주입
    if _safe_content:
        if lang == "en":
            user_content += f"\n\n<transcript>\n{_safe_content}\n</transcript>\nReflect the key facts and themes from the transcript above in your new plan."
        elif lang == "es":
            user_content += f"\n\n<transcript>\n{_safe_content}\n</transcript>\nRefleja los hechos y temas clave de la transcripción anterior en tu nuevo plan."
        else:
            user_content += f"\n\n<transcript>\n{_safe_content}\n</transcript>\n위 자막의 핵심 팩트와 주제를 반영하여 새로운 기획안을 작성하세요."
    if fact_context:
        if lang == "en":
            user_content += f"\n\n{fact_context}\n[Fact-Check Instruction] Prioritize facts from the reference above over your training data. Do NOT invent statistics — use only verified numbers."
        elif lang == "es":
            user_content += f"\n\n{fact_context}\n[Verificación de datos] Prioriza los datos de la referencia anterior. NO inventes estadísticas — usa solo datos verificados."
        else:
            user_content += f"\n\n{fact_context}\n[팩트체크 지시] 위 검색 결과의 팩트를 우선 활용하세요. 통계나 수치를 지어내지 마세요 — 검증된 정보만 사용하세요."

    # 채널별 훅 스타일 — fact_context 뒤에 주입 (LLM이 후반부를 더 강하게 반영)
    channel_hook_rules = _get_channel_hook_rules(channel, lang)
    if channel_hook_rules:
        user_content += f"\n\n{channel_hook_rules}\n[Critical] This rule applies MOST strongly to Cut 1. Different channels must have visibly different first-line energy."
    channel_title_rules = _get_channel_title_rules(channel)
    if channel_title_rules:
        user_content += f"\n\n{channel_title_rules}\n[Critical] The output title MUST follow this formula. Generic 'secret/truth/TOP 3' shells without a concrete subject are forbidden."
    channel_cut1_scene_rules = _get_channel_cut1_scene_rules(channel)
    if channel_cut1_scene_rules:
        user_content += f"\n\n{channel_cut1_scene_rules}\n[Critical] Cut 1 image_prompt and Cut 1 script must feel like the same scroll-stopping idea."

    # 레퍼런스 영상 분석 주입 (XML 구조화)
    if reference_url:
        try:
            from modules.utils.youtube_extractor import extract_youtube_reference
            ref_data = extract_youtube_reference(reference_url)
            if ref_data:
                ref_block = "\n\n<reference_analysis>"
                if ref_data.get("title"):
                    ref_block += f"\n  <source>{ref_data['title']}</source>"
                struct = ref_data.get("structure", {})
                if struct.get("hook"):
                    ref_block += f"\n  <hook_technique>{struct['hook']}</hook_technique>"
                if struct.get("ending"):
                    ref_block += f"\n  <ending_technique>{struct['ending']}</ending_technique>"
                if struct.get("style"):
                    ref_block += f"\n  <tone>{struct['style']}</tone>"
                if ref_data.get("transcript"):
                    # 첫 문장 + 마지막 문장 + 중간 피벗만 추출
                    sentences = [s.strip() for s in re.split(r"[.!?。？！]\s*", ref_data["transcript"]) if s.strip()]
                    key_parts = []
                    if sentences:
                        key_parts.append(sentences[0])
                    if len(sentences) > 2:
                        key_parts.append(sentences[len(sentences)//2])
                    if len(sentences) > 1:
                        key_parts.append(sentences[-1])
                    ref_block += f"\n  <key_sentences>{'. '.join(key_parts)}.</key_sentences>"
                ref_block += "\n</reference_analysis>"
                if lang == "en":
                    ref_block += "\n[Reference Instruction] Use the hook_technique/ending_technique/tone above as reference, but write completely original content. No copying."
                else:
                    ref_block += "\n[레퍼런스 활용 지시] 위 분석의 hook_technique/ending_technique/tone을 참고하되 내용은 완전히 새롭게 써라. 복사 금지."
                user_content += ref_block
        except Exception as e:
            print(f"[레퍼런스 분석] 실패, 무시하고 진행: {e}")

    # 429 자동 키 전환: 실패한 키를 차단하고 다른 키로 재시도
    exhausted_keys: set[str] = set()
    current_key = final_api_key
    cuts: list[dict[str, Any]] = []
    title: str = ""
    tags: list[str] = []
    last_error: Exception | None = None

    if llm_provider == "gemini":
        from modules.utils.keys import get_google_key, mark_key_exhausted, mask_key
        from modules.utils.gemini_client import get_current_sa_key, mark_sa_key_blocked
        max_key_attempts = 10
    else:
        max_key_attempts = 3
    parse_failures = 0  # JSON 파싱 실패 카운터 (429 카운터와 분리)
    for attempt in range(max_key_attempts):
        try:
            cuts, title, tags, video_description = _request_cuts(llm_provider, current_key, system_prompt, user_content, model_override=llm_model)
            break  # 성공
        except ValueError as ve:
            # JSON 파싱 실패 — 최대 2회 재시도 (429 카운터와 별개)
            parse_failures += 1
            last_error = ve
            if parse_failures <= 2:
                print(f"  [JSON 파싱 실패] 재시도 {parse_failures}/2... ({ve})")
                continue
            raise
        except Exception as e:
            last_error = e
            err_str = str(e)
            is_retryable = (
                "429" in err_str or "RESOURCE_EXHAUSTED" in err_str
                or "503" in err_str or "UNAVAILABLE" in err_str
                or "quota" in err_str.lower() or "rate_limit" in err_str.lower()
            )

            if is_retryable and llm_provider == "gemini":
                if os.getenv("GEMINI_BACKEND") == "vertex_ai":
                    # Vertex AI는 SA 인증을 사용하므로 API 키 대신 현재 SA를 차단하고 재시도한다.
                    _sa_key = get_current_sa_key()
                    if _sa_key:
                        mark_sa_key_blocked(_sa_key, block_seconds=60)
                        print("  [Vertex SA 전환] 현재 서비스 계정 차단 후 재시도")
                    time.sleep(min(2 ** (attempt + 1), 10))
                    current_key = None
                    continue
                mark_key_exhausted(current_key, service="gemini")
                exhausted_keys.add(current_key)
                # Vertex AI SA 키 블록 (429 시 자동 로테이션)
                _sa_key = get_current_sa_key()
                if _sa_key:
                    mark_sa_key_blocked(_sa_key, block_seconds=60)
                next_key = get_google_key(None, service="gemini", exclude=exhausted_keys)

                if next_key and next_key not in exhausted_keys:
                    print(f"  [키 전환] {mask_key(current_key)} → {mask_key(next_key)} (gemini 429 자동 전환)")
                    current_key = next_key
                    continue
                else:
                    # GPT 자동 폴백 비활성화 — Gemini만 사용
                    raise RuntimeError(f"[Gemini 할당량 초과] 등록된 모든 키({len(exhausted_keys)}개)의 쿼터가 소진되었습니다. 지출 한도를 확인하세요.") from e
            elif is_retryable:
                # OpenAI/Claude 429: 지수 백오프 후 재시도
                wait = min(2 ** (attempt + 1), 30) + random.uniform(0, 2)
                print(f"  [{provider_label} 429] {wait:.1f}초 후 재시도... ({attempt+1}/{max_key_attempts})")
                time.sleep(wait)
                continue
            else:
                raise  # 429가 아닌 에러는 그대로 전파

    # 전체 재시도 실패 시 마지막 에러 전파
    if not cuts and last_error:
        raise RuntimeError(f"[{provider_label}] 모든 재시도 실패 ({max_key_attempts}회)") from last_error

    # 채널×포맷별 min/max_cuts — 확장/트림 전에 먼저 계산
    from modules.utils.channel_config import get_channel_preset as _get_cuts_preset
    _cuts_preset = _get_cuts_preset(channel) if channel else None
    _format_cuts = (_cuts_preset or {}).get("format_cuts", {}).get(format_type or "", {}) if format_type else {}
    _cfg_max = _format_cuts.get("max") or (_cuts_preset or {}).get("max_cuts", 10)
    _cfg_min = _format_cuts.get("min") or (_cuts_preset or {}).get("min_cuts", 8)
    if _format_cuts:
        print(f"-> [포맷 컷 수] {format_type} × {channel}: {_cfg_min}~{_cfg_max}컷 적용")

    # 컷 수 검증 — 초과 시 트림, 부족 시 기존 컷 기반 확장 요청 (전체 재생성 방지)
    if len(cuts) > _cfg_max:
        print(f"-> [검증] 컷 수 {len(cuts)}개 → {_cfg_max}개로 트림")
        cuts = cuts[:_cfg_max]
    elif len(cuts) < _cfg_min:
        _fmt_label = f"[{format_type}] " if format_type else ""
        print(f"-> [검증 실패] {_fmt_label}컷 수가 {len(cuts)}개입니다. 기존 컷 기반 확장 요청합니다 (목표: {_cfg_min}~{_cfg_max}컷).")
        if llm_provider == "gemini":
            retry_key = get_google_key(None, service="gemini", exclude=exhausted_keys) or current_key
        else:
            retry_key = current_key
        # system_prompt에는 이미 포맷 규칙이 주입되어 있으므로 확장 요청에서는 그대로 재사용한다.
        retry_system = system_prompt
        # 기존 컷 데이터를 포함하여 확장만 요청 (전체 재생성 대신)
        existing_cuts_json = json.dumps(
            [{"script": c["script"], "description": c.get("text", ""), "image_prompt": c.get("prompt", "")} for c in cuts],
            ensure_ascii=False
        )
        if lang == "en":
            retry_expansion = (
                f"\n\nOnly {len(cuts)} cuts were generated. Expand to {_cfg_min}-{_cfg_max} total cuts. "
                f"You MUST keep ALL existing cuts verbatim and add NEW cuts between them to reinforce buildup/climax. Preserve the channel-specific hook style of Cut 1. "
                f"Return the complete expanded array.\nExisting cuts: {existing_cuts_json}"
            )
        elif lang == "es":
            retry_expansion = (
                f"\n\nSolo se generaron {len(cuts)} cortes. Expande a {_cfg_min}-{_cfg_max} cortes en total. "
                f"DEBES mantener TODOS los cortes existentes tal cual y agregar cortes NUEVOS entre ellos para reforzar el clímax. Conserva el estilo de gancho del corte 1 según el canal. "
                f"Devuelve el array completo expandido.\nCortes existentes: {existing_cuts_json}"
            )
        else:
            retry_expansion = (
                f"\n\n기존에 {len(cuts)}컷만 생성되었습니다. 총 {_cfg_min}~{_cfg_max}컷으로 확장하세요. "
                f"기존 컷은 반드시 그대로 유지하고, 사이에 새 컷을 추가하여 빌드업/클라이맥스를 보강하세요. 컷1의 채널별 훅 스타일은 그대로 유지하세요. "
                f"확장된 전체 배열을 반환하세요.\n기존 컷: {existing_cuts_json}"
            )
        if lang == "en":
            retry_user = f"Topic: '{_safe_title}'." + retry_expansion
        elif lang == "es":
            retry_user = f"Tema: '{_safe_title}'." + retry_expansion
        else:
            retry_user = f"주제: '{_safe_title}'." + retry_expansion
        _original_cuts = cuts[:]
        try:
            expanded_cuts, title, tags, _ = _request_cuts(llm_provider, retry_key, retry_system, retry_user, model_override=llm_model)
            original_scripts = {c["script"].strip()[:30] for c in _original_cuts}
            expanded_scripts = {c["script"].strip()[:30] for c in expanded_cuts}
            preserved = original_scripts & expanded_scripts
            if len(expanded_cuts) >= _cfg_min and len(preserved) >= len(original_scripts) * 0.7:
                cuts = expanded_cuts
                print(f"OK [컷 확장] {len(_original_cuts)}컷 → {len(cuts)}컷 (기존 {len(preserved)}/{len(original_scripts)}개 보존)")
            elif len(expanded_cuts) < _cfg_min:
                print(f"  [컷 확장 부족] {len(expanded_cuts)}컷 — 최소 {_cfg_min}컷 미달")
            else:
                print(f"  [컷 확장 실패] 기존 컷 보존율 낮음 ({len(preserved)}/{len(original_scripts)}) — 원본 유지")
        except Exception as retry_err:
            err_str = str(retry_err)
            if llm_provider == "gemini" and ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str):
                mark_key_exhausted(retry_key, service="gemini")
                print(f"  [컷 수 재시도 429] {mask_key(retry_key)} 차단됨 — 기존 {len(cuts)}컷으로 진행")
            else:
                raise

    if len(cuts) < _cfg_min:
        exact_text = f"exactly {_cfg_min}" if _cfg_min == _cfg_max else f"between {_cfg_min} and {_cfg_max}"
        print(f"-> [컷 수 강제 재생성] {len(cuts)}컷 → 목표 {_cfg_min}~{_cfg_max}컷")
        if lang == "en":
            strict_user = (
                f"Topic: '{_safe_title}'. Regenerate the entire short-form video plan. "
                f"Return {exact_text} cuts. Do not return fewer cuts. "
                "Each cut needs script, description, and image_prompt. Preserve the format structure and channel style."
            )
        elif lang == "es":
            strict_user = (
                f"Tema: '{_safe_title}'. Regenera todo el plan del video corto. "
                f"Devuelve {exact_text} cortes. No devuelvas menos cortes. "
                "Cada corte necesita script, description e image_prompt. Conserva la estructura del formato y el estilo del canal."
            )
        else:
            strict_user = (
                f"주제: '{_safe_title}'. 숏폼 기획안을 전체 재생성하세요. "
                f"반드시 {_cfg_min}~{_cfg_max}컷으로 반환하고, 최소 컷보다 적게 반환하지 마세요. "
                "각 컷에는 script, description, image_prompt가 모두 필요합니다. 포맷 구조와 채널 스타일을 유지하세요."
            )
        if fact_context:
            strict_user += f"\n\n{fact_context}"
        try:
            retry_key = (get_google_key(None, service="gemini", exclude=exhausted_keys) or current_key) if llm_provider == "gemini" else current_key
            regen_cuts, regen_title, regen_tags, regen_description = _request_cuts(
                llm_provider,
                retry_key,
                retry_system if "retry_system" in locals() else system_prompt,
                strict_user,
                model_override=llm_model,
            )
            if len(regen_cuts) > _cfg_max:
                print(f"-> [컷 수 강제 재생성] {len(regen_cuts)}컷 → {_cfg_max}개로 트림")
                regen_cuts = regen_cuts[:_cfg_max]
            if len(regen_cuts) >= _cfg_min:
                cuts = regen_cuts
                title = regen_title or title
                tags = regen_tags or tags
                video_description = regen_description or video_description
                print(f"OK [컷 수 강제 재생성] {len(cuts)}컷 확보")
        except Exception as regen_err:
            err_str = str(regen_err)
            if llm_provider == "gemini" and ("429" in err_str or "RESOURCE_EXHAUSTED" in err_str):
                mark_key_exhausted(retry_key, service="gemini")
                print(f"  [컷 수 강제 재생성 429] {mask_key(retry_key)} 차단됨")
            else:
                raise

    if len(cuts) < _cfg_min:
        raise ValueError(f"[HARD FAIL] 컷 수 {len(cuts)}개 — 채널 최소 {_cfg_min}컷 미달. 스크립트 재생성 필요.")

    # title이 비어있으면 제목을 폴백으로 사용 (자막 포함 방지)
    if not title:
        title = _topic_title

    # tags 기본값 보장 + #Shorts/#쇼츠 금지 + 5개 제한
    if not tags or not isinstance(tags, list):
        tags = []
    _BANNED_TAG_STEMS = {"shorts", "쇼츠"}
    tags = [t for t in tags if t.lower().lstrip("#") not in _BANNED_TAG_STEMS]
    tags = tags[:5]

    # ── 3단계 검증 파이프라인 (최대 1회 재검증, 무한 루프 방지) ──
    # v2 오케스트라: _skip_verify=True면 QualityAgent가 별도 실행
    # 검증용 키: Gemini는 fresh 키 사용 (생성 후 429 위험 회피)
    def _verify_key():
        if llm_provider == "gemini":
            fresh = get_google_key(None, service="gemini", exclude=exhausted_keys)
            return fresh or current_key
        return current_key

    if not _skip_verify:
        # 순서: ① 하이네스 구조 → ② 주제 일치 → (구조가 스크립트를 바꿨으면 주제 재검증 1회)→ ③ 팩트
        _scripts_before = [c["script"] for c in cuts]

        # ① 하이네스 구조 검증 (Hook/충격체인/루프엔딩)
        cuts = _verify_highness_structure(cuts, _topic_title, llm_provider, _verify_key(), lang, llm_model, channel)

        # ② 주제-이미지 일치 검증
        cuts = _verify_subject_match(cuts, _topic_title, llm_provider, _verify_key(), lang, llm_model)

        # ②-b 구조 수정이 스크립트를 바꿨으면 → 주제 재검증 1회만 (무한 루프 차단)
        _scripts_after = [c["script"] for c in cuts]
        if _scripts_before != _scripts_after:
            print("-> [재검증] 구조/주제 수정으로 스크립트 변경됨 → 주제 일치 재검증 (1회)")
            cuts = _verify_subject_match(cuts, _topic_title, llm_provider, _verify_key(), lang, llm_model)

        # ③ 팩트 검증 (조건부 — 고위험 주제+포맷만)
        if _should_run_fact_verify(_topic_title, format_type, fact_context):
            cuts = _verify_facts(cuts, fact_context, _topic_title, llm_provider, _verify_key(), lang, llm_model)
        elif fact_context:
            print(f"  [팩트 검증] 스킵 — 저위험 주제/포맷")

        # ④ HARD FAIL 검증 (코드 레벨 품질 게이트) — 실패 시 1회 구조 수정 재시도
        # format_type을 각 컷에 첨부 (포맷별 HARD FAIL 검증용)
        if format_type:
            for _c in cuts:
                _c["format_type"] = format_type.upper()
                _c["topic"] = _topic_title
            _ensure_format_metadata_tags(cuts, format_type)
        hard_fails = _validate_hard_fail(cuts, channel)

        # ⑤ 내러티브 아크 검증 — HOOK/LOOP/CLIMAX/PIVOT/RELEASE 구조 체크
        arc_issues = _validate_narrative_arc(cuts, lang)
        if arc_issues:
            print(f"⚠️ [아크 검증] {len(arc_issues)}개 구조 문제:")
            for issue in arc_issues:
                print(f"  - {issue}")
            # 아크 문제 → 구조 검증으로 1회 자동 수정
            has_hook_fail = any("ARC_HOOK" in i for i in arc_issues)
            has_loop_fail = any("ARC_LOOP" in i for i in arc_issues)
            # 컷1/마지막 컷 문제만 구조 검증으로 자동 수정 (중간 컷은 건드리지 않음)
            if has_hook_fail or has_loop_fail:
                print("-> [아크 수정] 훅/루프 구조 검증으로 자동 수정 시도...")
                cuts = _verify_highness_structure(cuts, _topic_title, llm_provider, _verify_key(), lang, llm_model, channel)
                _ensure_format_metadata_tags(cuts, format_type)
                arc_issues_retry = _validate_narrative_arc(cuts, lang)
                if arc_issues_retry:
                    print(f"  [아크] 수정 후 {len(arc_issues_retry)}개 남음 — 결과 유지")
                else:
                    print("OK [아크] 자동 수정 성공")
            # 중간 컷 문제(CLIMAX/PIVOT/RELEASE)는 경고만
            _mid_issues = [i for i in arc_issues if any(k in i for k in ("ARC_CLIMAX", "ARC_PIVOT", "ARC_RELEASE"))]
            if _mid_issues:
                print(f"  [아크 경고] 중간 컷 구조 {len(_mid_issues)}건 — 수동 확인 권장 (자동 수정 생략)")
        else:
            print("OK [아크 검증] HOOK/LOOP/CLIMAX/PIVOT/RELEASE 통과")

        region_warns = _validate_region_style(cuts, channel)
        if hard_fails:
            print(f"⚠️ [HARD FAIL] {len(hard_fails)}개 품질 문제 감지:")
            for fail in hard_fails:
                print(f"  - {fail}")
            # HARD FAIL 유형별 수정 라우팅
            has_visual_fail = any("VISUAL" in f for f in hard_fails)
            has_structure_fail = any(k in "".join(hard_fails) for k in ["HOOK_WEAK", "LOOP", "TONE"])
            has_academic_fail = any("ACADEMIC" in f for f in hard_fails)
            if has_academic_fail:
                print("-> [HARD FAIL 수정] 학술체 리라이트 시도...")
                cuts = _rewrite_academic_tone(cuts, lang, llm_provider, _verify_key(), llm_model)
            if has_structure_fail:
                print("-> [HARD FAIL 수정] 구조 검증으로 자동 수정 시도 (1회)...")
                cuts = _verify_highness_structure(cuts, _topic_title, llm_provider, _verify_key(), lang, llm_model, channel)
                _ensure_format_metadata_tags(cuts, format_type)
            if has_visual_fail:
                print("-> [HARD FAIL 수정] 이미지 프롬프트 검증으로 자동 수정 시도 (1회)...")
                cuts = _verify_subject_match(cuts, _topic_title, llm_provider, _verify_key(), lang, llm_model)
            # 재검증
            hard_fails_retry = _validate_hard_fail(cuts, channel)
            if hard_fails_retry:
                fail_text = "\n".join(f"- {f}" for f in hard_fails_retry)
                raise ValueError(f"[HARD FAIL] 자동 수정 후에도 품질 문제가 남았습니다.\n{fail_text}")
            else:
                print(f"OK [HARD FAIL] 자동 수정으로 모든 품질 문제 해결")
        if region_warns:
            print(f"⚠️ [REGION STYLE] {len(region_warns)}개 지역 스타일 경고:")
            for warn in region_warns:
                print(f"  - {warn}")
        if not hard_fails and not region_warns:
            print(f"OK [품질 게이트] HARD FAIL 통과 | 지역 스타일 통과")
    else:
        print(f"[v2] 검증 스킵 (QualityAgent가 별도 실행)")

    # ── 비주얼 디렉터: image_prompt 전문 리라이트 (컷1 특별 강화) ──
    if not _skip_visual_director:
        try:
            _vd_key = _verify_key()
            cuts = _enhance_image_prompts(cuts, _topic_title, lang, _vd_key, channel, format_type)
            cuts = ensure_visual_prompts_in_english(cuts, _topic_title, _vd_key, channel, format_type)
            # 비주얼 디렉터 후 주제 일치 재검증 (공룡 같은 무관 피사체 방지)
            cuts = _verify_subject_match(cuts, _topic_title, llm_provider, _verify_key(), lang, llm_model)
            cuts = ensure_visual_prompts_in_english(cuts, _topic_title, _vd_key, channel, format_type)
        except Exception as _vd_err:
            print(f"[비주얼 디렉터] 스킵 (원본 유지): {_vd_err}")
    else:
        print(f"[v2] 비주얼 디렉터 스킵 (VisualDirectorAgent가 별도 실행)")

    print(f"OK [기획 전문가] 기획안 완성! ({len(cuts)}컷, {provider_label}) 제목: {title} | 태그: {', '.join(tags)}")

    # ── 채널 금지 표현 필터링 + 문장 자연화 ──
    if not _skip_polish:
        from modules.utils.channel_config import get_channel_preset
        _ch_preset = get_channel_preset(channel) if channel else None
        _forbidden = (_ch_preset or {}).get("forbidden_phrases", [])
        if _forbidden and cuts:
            for _ci, _cut in enumerate(cuts):
                _scr = _cut.get("script", "")
                for _fp in _forbidden:
                    if _fp.lower() in _scr.lower():
                        _scr = re.sub(re.escape(_fp), "", _scr, flags=re.IGNORECASE).strip()
                        _scr = re.sub(r"\s{2,}", " ", _scr)
                if _scr != _cut.get("script", ""):
                    cuts[_ci]["script"] = _scr
                    print(f"[금지 표현] Cut {_ci+1} 필터링됨")

        # ── 문장 자연화 리라이트 ──
        _pre_polish_mid = cuts[3].get("script", "") if len(cuts) > 3 else ""
        _pre_polish_last = cuts[-1].get("script", "") if cuts else ""
        try:
            _polish_key = _verify_key()
            cuts, _polish_notes = polish_scripts(
                cuts=cuts, lang=lang, channel=channel,
                llm_provider=llm_provider, api_key=_polish_key,
                llm_model=llm_model,
                skip_indices=[0],  # 컷1(훅) 보존
            )
            if _polish_notes:
                print(f"[문장 자연화] 적용됨")
        except Exception as _pe:
            print(f"[문장 자연화] 스킵 (원본 유지): {_pe}")

        # ── polish 후 핵심 컷 재검사 (리텐션/루프 약화 방지) ──
        # 컷1은 skip_indices=[0]으로 polish에서 제외되므로 복원 불필요
        if cuts:
            _post_mid = cuts[3].get("script", "") if len(cuts) > 3 else ""
            _post_last = cuts[-1].get("script", "")
            # Cut 4 (리텐션 락): 약해졌으면 원본 복원
            if len(cuts) > 3 and _pre_polish_mid and _post_mid and len(_post_mid) > len(_pre_polish_mid) * 1.3:
                cuts[3]["script"] = _pre_polish_mid
                print(f"[재검사] Cut 4 리텐션 락 복원")
            # 마지막 컷 (루프): 미완성 문장으로 바뀌었으면 원본 복원
            _bad_endings = ["...", "사실은", "근데 진짜", "actually", "but then", "en realidad"]
            if _post_last and any(_post_last.rstrip().endswith(p) for p in _bad_endings):
                cuts[-1]["script"] = _pre_polish_last
                print(f"[재검사] 마지막 컷 루프 복원 — 미완성 문장 감지")

        if format_type:
            for _c in cuts:
                _c["format_type"] = format_type.upper()
                _c["topic"] = _topic_title
            _ensure_format_metadata_tags(cuts, format_type)
        _post_polish_fails = _validate_hard_fail(cuts, channel)
        if _post_polish_fails:
            fail_text = "\n".join(f"- {f}" for f in _post_polish_fails)
            raise ValueError(f"[HARD FAIL] post-polish 이후 품질 문제가 발생했습니다.\n{fail_text}")

        # ── polish 후 금지 표현 재필터링 ──
        if _forbidden and cuts:
            for _ci, _cut in enumerate(cuts):
                _scr = _cut.get("script", "")
                for _fp in _forbidden:
                    if _fp.lower() in _scr.lower():
                        _scr = re.sub(re.escape(_fp), "", _scr, flags=re.IGNORECASE).strip()
                        _scr = re.sub(r"\s{2,}", " ", _scr)
                if _scr != _cut.get("script", ""):
                    cuts[_ci]["script"] = _scr
                    print(f"[금지 표현 재필터] Cut {_ci+1}")
    else:
        print(f"[v2] 폴리시 스킵 (PolishAgent가 별도 실행)")

    # v2 오케스트라 모드: fact_context도 반환 (QualityAgent에서 사용)
    if _skip_verify or _skip_polish or _skip_visual_director:
        if format_type:
            for _c in cuts:
                _c["format_type"] = format_type.upper()
                _c["topic"] = _topic_title
            _ensure_format_metadata_tags(cuts, format_type)
        return cuts, topic_folder, title, tags, video_description, fact_context

    return cuts, topic_folder, title, tags, video_description, ""
