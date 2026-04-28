import re
from difflib import SequenceMatcher
from .parser import _VALID_EMOTIONS


# ── HARD FAIL 검증 (코드 레벨 품질 게이트) ──────────────────────────

_WEAPON_TOPIC_PATTERN = re.compile(r"(무기|weapon|weapons|arma|armas)", re.IGNORECASE)
_WEAPON_SCRIPT_PATTERN = re.compile(
    r"(무기|발톱|턱|이빨|치아|송곳니|꼬리\s*곤봉|꼬리곤봉|뿔|가시|bite|bite force|jaw|jaws|teeth|tooth|fang|claw|claws|talon|talons|horn|horns|spike|spikes|tail club|clubbed tail|weapon|weapons|arma|armas|garra|garras|diente|dientes|colmillo|colmillos|mordida|mandibula|mandíbula|mandibulas|mandíbulas|cola|cuerno|cuernos|espina|espinas)",
    re.IGNORECASE,
)
_KOREAN_STIFF_ENDING_PATTERN = re.compile(r"(입니다|합니다|였습니다|했습니다|그 자체)([.!?…]?)$")
_KOREAN_REPEAT_PHRASE_PATTERN = re.compile(r"[가-힣A-Za-z]{3,}")
_COUNTDOWN_RANK_PATTERN = re.compile(
    r"(?:#?\s*(\d{1,2})\s*(?:위|등|번째|st|nd|rd|th|°|lugar)\b)|(?:\b(top)\s*(\d{1,2})\b)|(?:\b(number|no\.)\s*(\d{1,2})\b)",
    re.IGNORECASE,
)


def _looks_like_weapon_topic(cuts: list[dict]) -> bool:
    if not cuts:
        return False
    topic = (
        cuts[0].get("topic")
        or cuts[0].get("topic_title")
        or cuts[0].get("title")
        or ""
    )
    return bool(_WEAPON_TOPIC_PATTERN.search(topic))


def _countdown_target_n(cuts: list[dict]) -> int | None:
    topic = " ".join(
        str(cuts[0].get(k, "") or "")
        for k in ("topic", "topic_title", "title", "script")
    ) if cuts else ""
    m = re.search(r"\btop\s*(\d{1,2})\b|TOP\s*(\d{1,2})|(\d{1,2})\s*(?:개|가지|위)", topic, re.IGNORECASE)
    if not m:
        return 3 if _looks_like_weapon_topic(cuts) else None
    for group in m.groups():
        if group:
            return int(group)
    return None


def _extract_countdown_rank(text: str) -> int | None:
    match = _COUNTDOWN_RANK_PATTERN.search(text or "")
    if not match:
        return None
    for group in match.groups():
        if group and group.isdigit():
            return int(group)
    return None


def _is_spoken_korean_channel(channel: str | None) -> bool:
    return (channel or "").lower() == "askanything"


def _normalize_script_for_similarity(text: str) -> str:
    text = re.sub(r"[^\w\s가-힣]", " ", (text or "").lower())
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _shared_long_tokens(a: str, b: str) -> set[str]:
    tokens_a = {t for t in _normalize_script_for_similarity(a).split() if len(t) >= 3}
    tokens_b = {t for t in _normalize_script_for_similarity(b).split() if len(t) >= 3}
    return tokens_a & tokens_b


def _shared_opening_tokens(a: str, b: str, limit: int = 4) -> list[str]:
    tokens_a = [t for t in _normalize_script_for_similarity(a).split() if len(t) >= 2][:limit]
    tokens_b = [t for t in _normalize_script_for_similarity(b).split() if len(t) >= 2][:limit]
    shared: list[str] = []
    for ta, tb in zip(tokens_a, tokens_b):
        if ta != tb:
            break
        shared.append(ta)
    return shared


def _shared_token_phrases(a: str, b: str, n: int = 2) -> set[str]:
    tokens_a = [t for t in _normalize_script_for_similarity(a).split() if len(t) >= 2]
    tokens_b = [t for t in _normalize_script_for_similarity(b).split() if len(t) >= 2]
    phrases_a = {" ".join(tokens_a[i:i+n]) for i in range(len(tokens_a) - n + 1)}
    phrases_b = {" ".join(tokens_b[i:i+n]) for i in range(len(tokens_b) - n + 1)}
    return {p for p in (phrases_a & phrases_b) if len(p.replace(" ", "")) >= 4}

def _validate_hard_fail(cuts: list[dict], channel: str | None = None) -> list[str]:
    """프롬프트의 HARD FAIL 조건을 코드로 검증. 실패 항목 리스트 반환 (빈 리스트 = 통과)."""
    if not cuts or len(cuts) < 3:
        return []

    failures: list[str] = []

    # 1) Hook 검증 — 약한/뻔한 훅만 차단 (강한 질문형은 허용)
    first_script = cuts[0].get("script", "")
    weak_hook_patterns = [
        "did you know", "sabías que", "알고 있", "오늘 소개",
        "today we", "have you ever", "¿sabías", "한번 알아",
        "let me tell", "들어봤", "이번에는",
        "in this video", "en este video", "이 영상에서",
    ]
    if any(p in first_script.lower() for p in weak_hook_patterns):
        failures.append(f"HOOK_WEAK: 첫 컷이 약한 패턴 포함 — '{first_script[:50]}'")

    warnings: list[str] = []
    channel_name = (channel or "").lower().strip()
    if channel_name in {"wonderdrop", "prismtale"} and "?" in first_script:
        warnings.append(f"HOOK_STYLE_CHANNEL: {channel_name} 컷1은 질문형보다 선언형이 더 강함 — '{first_script[:40]}'")
    if channel_name == "exploratodo" and len(first_script.split()) < 4:
        warnings.append(f"HOOK_STYLE_CHANNEL: exploratodo 컷1이 너무 짧아 긴박감이 약할 수 있음 — '{first_script[:40]}'")

    # 1-b) Hook 길이 — 채널별 Cut1 글자/단어 수 (경고 전용, 하드 fail 아님)
    if channel:
        from modules.utils.channel_config import get_channel_preset as _get_hook_preset
        _hook_preset = _get_hook_preset(channel)
        _hook_lang = (_hook_preset or {}).get("language", "en")
        if _hook_lang == "ko":
            if len(first_script.replace(" ", "")) > 20:
                warnings.append(f"HOOK_TOO_LONG: KO 훅 {len(first_script.replace(' ', ''))}자 (최대 20자) — '{first_script[:30]}'")
        elif _hook_lang == "en":
            word_count = len(first_script.split())
            if word_count > 10:
                warnings.append(f"HOOK_TOO_LONG: EN 훅 {word_count}단어 (최대 10) — '{first_script[:40]}'")
        elif _hook_lang == "es":
            word_count = len(first_script.split())
            if word_count > 12:
                warnings.append(f"HOOK_TOO_LONG: ES 훅 {word_count}단어 (최대 12) — '{first_script[:40]}'")

    # 2) 긴장 상승 — 감정 태그 다양성 (경고 전용, 하드 fail 아님)
    emotions: list[tuple[int, str]] = []  # (컷 인덱스, 태그)
    for ci, c in enumerate(cuts):
        desc = c.get("text", "") or c.get("description", "")
        for tag in ["SHOCK", "WONDER", "TENSION", "REVEAL", "URGENCY", "DISBELIEF", "IDENTITY", "LOOP", "CALM"]:
            if tag in desc.upper():
                emotions.append((ci, tag))
                break
    unique_tags = {t for _, t in emotions}
    if len(unique_tags) < 3:
        warnings.append(f"TENSION_FLAT: 감정 태그 {len(unique_tags)}종류 (최소 3 필요)")
    # 2연속 동일 감정 태그 체크 (경고만, 자동 수정 없음)
    for i in range(1, len(emotions)):
        if emotions[i][1] == emotions[i-1][1]:
            warnings.append(f"EMOTION_REPEAT: 컷 {emotions[i-1][0]+1}~{emotions[i][0]+1} 동일 태그 [{emotions[i][1]}] 연속")

    # 3) 루프 연결 검증 — 마지막 컷이 미완성 문장인지
    last_script = cuts[-1].get("script", "")
    bad_endings = ["...", "사실은", "근데 진짜", "actually", "but then", "en realidad"]
    if any(last_script.rstrip().endswith(p) for p in bad_endings):
        failures.append(f"LOOP_INCOMPLETE: 마지막 컷 미완성 — '{last_script[:50]}'")
    bad_cta = ["다음에", "next time", "la próxima", "알려줄게", "i'll show"]
    if any(p in last_script.lower() for p in bad_cta):
        failures.append(f"LOOP_CTA: 마지막 컷에 빈 약속 CTA — '{last_script[:50]}'")

    # 3-b) [LOOP] 태그 공통 검증 — 마지막 컷에 [LOOP] 존재 필수 (EMOTIONAL_SCI 제외)
    fmt_type = (cuts[0].get("format_type", "") or "").upper() if cuts else ""
    if fmt_type and fmt_type not in ("EMOTIONAL_SCI", "MYSTERY"):
        last_desc = cuts[-1].get("description", cuts[-1].get("text", ""))
        if "LOOP" not in last_desc.upper():
            failures.append(f"LOOP_MISSING: 마지막 컷에 [LOOP] 태그 없음 — 루프 엔딩 필수 ({fmt_type})")

    # 4) 이미지 임팩트 검증 — Cut 1에 시각적 키워드 있는지
    first_prompt = cuts[0].get("prompt", "").lower()
    impact_keywords = [
        "dramatic", "extreme", "contrast", "surreal", "glowing", "massive",
        "tiny", "vibrant", "dark", "neon", "cinematic", "sharp", "intense",
        "colossal", "macro", "aerial", "deep", "vast", "bright", "enormous",
        "pitch-black", "bioluminescent", "mysterious", "shadow", "golden",
    ]
    if not any(kw in first_prompt for kw in impact_keywords):
        failures.append(f"VISUAL_WEAK: Cut 1 image_prompt에 임팩트 키워드 없음")

    # 5) 학술체 감지 — "연구에 따르면" 등 학술적 도입부
    academic_patterns_ko = ["연구에 따르면", "과학자들이 발견", "에 의하면", "것으로 밝혀", "것으로 알려져", "분석에 따르면", "논문에 따르면"]
    academic_patterns_en = ["according to", "studies show", "researchers found", "scientists discovered", "research suggests", "a study published"]
    academic_patterns_es = ["según estudios", "los científicos descubrieron", "investigaciones demuestran", "un estudio publicado"]
    _academic_flagged: set[int] = set()
    for pat in academic_patterns_ko + academic_patterns_en + academic_patterns_es:
        for ci, c in enumerate(cuts):
            if ci not in _academic_flagged and pat.lower() in c.get("script", "").lower():
                failures.append(f"ACADEMIC_TONE: Cut {ci+1}에 학술체 '{pat}' — '{c['script'][:50]}'")
                _academic_flagged.add(ci)

    # 6) 스크립트 내용 중복 감지 — 같은 팩트 반복 방지
    if len(cuts) >= 4:
        scripts = [c.get("script", "") for c in cuts]
        for i in range(len(scripts)):
            if not scripts[i]:
                continue
            words_i = set(re.sub(r"[^\w\s]", "", scripts[i].lower()).split())
            words_i.discard("")
            if len(words_i) < 3:
                continue
            for j in range(i + 1, len(scripts)):
                if not scripts[j]:
                    continue
                words_j = set(re.sub(r"[^\w\s]", "", scripts[j].lower()).split())
                words_j.discard("")
                if len(words_j) < 3:
                    continue
                overlap = words_i & words_j
                ratio = len(overlap) / min(len(words_i), len(words_j))
                if ratio > 0.65:
                    failures.append(
                        f"CONTENT_REPEAT: 컷{i+1}↔컷{j+1} 내용 65%+ 중복 "
                        f"({len(overlap)}/{min(len(words_i), len(words_j))}단어 일치)"
                    )
                    continue

                normalized_i = _normalize_script_for_similarity(scripts[i])
                normalized_j = _normalize_script_for_similarity(scripts[j])
                if not normalized_i or not normalized_j:
                    continue

                seq_ratio = SequenceMatcher(None, normalized_i, normalized_j).ratio()
                shared_tokens = _shared_long_tokens(scripts[i], scripts[j])
                if seq_ratio >= 0.72 and len(shared_tokens) >= 2:
                    failures.append(
                        f"CONTENT_NEAR_REPEAT: 컷{i+1}↔컷{j+1} 표현만 바꾼 유사 반복 "
                        f"(유사도 {seq_ratio:.2f}, 공통어 {', '.join(sorted(shared_tokens)[:4])})"
                    )

    # 6-b) askanything 한국어 말투 검증 — 딱딱한 형식체 마무리 차단
    if _is_spoken_korean_channel(channel):
        for ci, c in enumerate(cuts):
            script = (c.get("script", "") or "").strip()
            if script and _KOREAN_STIFF_ENDING_PATTERN.search(script):
                failures.append(f"KOREAN_TONE_STIFF: 컷{ci+1} 한국어 말투가 딱딱함 — '{script[:50]}'")
        for ci in range(1, len(cuts)):
            prev_script = (cuts[ci - 1].get("script", "") or "").strip()
            curr_script = (cuts[ci].get("script", "") or "").strip()
            shared_tokens = _shared_long_tokens(prev_script, curr_script)
            shared_opening = _shared_opening_tokens(prev_script, curr_script)
            shared_phrases = _shared_token_phrases(prev_script, curr_script, n=2)
            if len(shared_tokens) >= 2:
                seq_ratio = SequenceMatcher(
                    None,
                    _normalize_script_for_similarity(prev_script),
                    _normalize_script_for_similarity(curr_script),
                ).ratio()
                if seq_ratio >= 0.6:
                    failures.append(
                        f"KOREAN_NEAR_REPEAT: 컷{ci}↔컷{ci+1} 비슷한 말 반복 "
                        f"(유사도 {seq_ratio:.2f}, 공통어 {', '.join(sorted(shared_tokens)[:4])})"
                    )
                    continue
            if len(shared_opening) >= 2:
                failures.append(
                    f"KOREAN_OPENING_REPEAT: 컷{ci}↔컷{ci+1} 문장 앞머리 반복 "
                    f"({ ' '.join(shared_opening) })"
                )
                continue
            if shared_phrases:
                failures.append(
                    f"KOREAN_PHRASE_REPEAT: 컷{ci}↔컷{ci+1} 핵심 구절 반복 "
                    f"({', '.join(sorted(shared_phrases)[:3])})"
                )

    # 7) 포맷별 구조 검증 (format_type은 line 71에서 이미 추출됨)

    if fmt_type == "WHO_WINS":
        # 컷1 [SHOCK] — 권장 (warning)
        first_desc = cuts[0].get("description", cuts[0].get("text", ""))
        if "SHOCK" not in first_desc.upper():
            warnings.append("FORMAT_WHO_WINS_SOFT: 컷1 [SHOCK] 태그 없음 — 대결 선언 강도 약할 수 있음")
        # 11컷 필수 (뼈대 — hard fail)
        if len(cuts) != 11:
            failures.append(f"FORMAT_WHO_WINS: {len(cuts)}컷 → 반드시 11컷 필요 (A소개2+B소개2+대결3+과학1+승자1+루프1+훅1)")
        # REVEAL이 컷9 이후에 있어야 함 (뼈대 — hard fail)
        for ci, c in enumerate(cuts[:min(8, len(cuts))]):
            desc = c.get("description", c.get("text", ""))
            if "REVEAL" in desc.upper():
                failures.append(f"FORMAT_WHO_WINS: 컷{ci+1} 조기 [REVEAL] — 승자는 컷9 이후 공개 필요")
                break

    elif fmt_type == "EMOTIONAL_SCI":
        # 컷1 [WONDER] — 권장 (warning)
        first_desc = cuts[0].get("description", cuts[0].get("text", ""))
        if "WONDER" not in first_desc.upper():
            warnings.append("FORMAT_EMOTIONAL_SCI_SOFT: 컷1 [WONDER] 태그 권장 — 감성과학의 몰입감이 약해질 수 있음")
        # 전체 컷에서 [SHOCK] 금지 (뼈대 — hard fail)
        for ci, c in enumerate(cuts):
            desc = c.get("description", "") or c.get("text", "")
            if "SHOCK" in desc.upper():
                failures.append(f"FORMAT_EMOTIONAL_SCI: 컷{ci+1} [SHOCK] 금지 — 감성과학 포맷은 SHOCK 사용 불가")
        # [WONDER] 또는 [IDENTITY] 최소 2컷 — 권장 (warning)
        warm_count = sum(
            1 for c in cuts
            if any(t in (c.get("description", "") or c.get("text", "")).upper()
                   for t in ("WONDER", "IDENTITY"))
        )
        if warm_count < 2:
            warnings.append(f"FORMAT_EMOTIONAL_SCI_SOFT: WONDER/IDENTITY 태그 {warm_count}컷 (권장 2+)")

    elif fmt_type == "IF":
        # 컷1 [SHOCK] — 권장 (warning)
        first_desc = cuts[0].get("description", cuts[0].get("text", ""))
        if "SHOCK" not in first_desc.upper():
            warnings.append("FORMAT_IF_SOFT: 컷1 [SHOCK] 태그 권장 — 가정 선언 임팩트가 약할 수 있음")
        # 연쇄 결과 컷: 0개는 포맷 붕괴 (hard fail), 1개는 권장 (warning)
        chain_tags = {"CHAIN", "ESCALATE", "BUILD"}
        chain_count = sum(
            1 for c in cuts
            if any(t in (c.get("description", "") or c.get("text", "")).upper() for t in chain_tags)
        )
        if chain_count == 0:
            failures.append("FORMAT_IF: 연쇄 결과 컷 0개 — IF 포맷은 최소 1개 CHAIN/ESCALATE 필수")
        elif chain_count < 2:
            warnings.append(f"FORMAT_IF_SOFT: 연쇄 결과 컷 {chain_count}개 (권장 2+)")

    elif fmt_type == "COUNTDOWN":
        # 컷1 [SHOCK] — 권장 (warning)
        first_desc = cuts[0].get("description", cuts[0].get("text", ""))
        if "SHOCK" not in first_desc.upper():
            warnings.append("FORMAT_COUNTDOWN_SOFT: 컷1 [SHOCK] 태그 권장 — TOP N 선언 임팩트 약화 가능")
        # [REVEAL] 태그 존재 확인 (뼈대 — hard fail)
        has_reveal = any("REVEAL" in (c.get("description", "") or c.get("text", "")).upper() for c in cuts)
        if not has_reveal:
            failures.append("FORMAT_COUNTDOWN: [REVEAL] 태그 없음 — 1위 공개 컷 필수")
        target_n = _countdown_target_n(cuts)
        ranked_items: list[tuple[int, int, str]] = []
        for ci, c in enumerate(cuts):
            script = c.get("script", "") or ""
            rank = _extract_countdown_rank(script)
            if rank:
                ranked_items.append((ci + 1, rank, script))
        if target_n:
            expected_ranks = set(range(1, target_n + 1))
            actual_ranks = {rank for _, rank, _ in ranked_items if rank in expected_ranks}
            if actual_ranks != expected_ranks:
                failures.append(
                    f"FORMAT_COUNTDOWN: TOP {target_n}인데 순위 컷이 정확하지 않음 "
                    f"(필요 {sorted(expected_ranks)}, 실제 {sorted(actual_ranks)})"
                )
            extra_ranks = [rank for _, rank, _ in ranked_items if rank > target_n]
            if extra_ranks:
                failures.append(f"FORMAT_COUNTDOWN: TOP {target_n} 범위 밖 순위 표기 감지 ({sorted(set(extra_ranks))})")
        elif len(ranked_items) < 3:
            warnings.append(f"FORMAT_COUNTDOWN_SOFT: 순위 표기 {len(ranked_items)}컷 (권장 3컷 이상)")
        if _looks_like_weapon_topic(cuts):
            weapon_lines = [
                (ci, rank, script) for ci, rank, script in ranked_items
                if _WEAPON_SCRIPT_PATTERN.search(script)
            ]
            required = target_n or 3
            if len(weapon_lines) < required:
                failures.append(f"FORMAT_COUNTDOWN_WEAPON: 무기 TOP {required}인데 무기 명칭이 직접 나온 순위 컷이 {len(weapon_lines)}개")

    elif fmt_type == "SCALE":
        # 컷1 [SHOCK] — 권장 (warning)
        first_desc = cuts[0].get("description", cuts[0].get("text", ""))
        if "SHOCK" not in first_desc.upper():
            warnings.append("FORMAT_SCALE_SOFT: 컷1 [SHOCK] 태그 권장 — 스케일 충격이 약할 수 있음")
        # 수치 밀도 — 권장 (warning)
        cuts_without_scale = sum(
            1 for c in cuts
            if not re.search(r'\d', c.get("script", ""))
        )
        if cuts_without_scale >= 2:
            warnings.append(f"FORMAT_SCALE_SOFT: 수치 없는 컷 {cuts_without_scale}개 (권장 최대 1개)")

    elif fmt_type == "PARADOX":
        # 컷1 [SHOCK] — 권장 (warning)
        first_desc = cuts[0].get("description", cuts[0].get("text", ""))
        if "SHOCK" not in first_desc.upper():
            warnings.append("FORMAT_PARADOX_SOFT: 컷1 [SHOCK] 태그 권장 — 통념 전복 임팩트 약화 가능")
        # 반전 횟수: 0개는 포맷 붕괴 (hard fail), 1개는 권장 (warning)
        reversal_count = sum(
            1 for c in cuts
            if any(t in (c.get("description", "") or c.get("text", "")).upper()
                   for t in ("REVEAL", "DISBELIEF"))
        )
        if reversal_count == 0:
            failures.append("FORMAT_PARADOX: 반전 0개 — PARADOX 포맷은 최소 1개 REVEAL/DISBELIEF 필수")
        elif reversal_count < 2:
            warnings.append(f"FORMAT_PARADOX_SOFT: 반전 {reversal_count}개 (권장 2단계 이상)")

    elif fmt_type == "FACT":
        # REVEAL 존재 (뼈대 — hard fail)
        has_reveal = any("REVEAL" in (c.get("description", "") or c.get("text", "")).upper() for c in cuts)
        if not has_reveal:
            failures.append("FORMAT_FACT: [REVEAL] 태그 없음 — 핵심 사실 공개 컷 필수")
        # 수치 밀도 — 권장 (warning)
        cuts_without_numbers = sum(
            1 for c in cuts
            if not re.search(r'\d', c.get("script", ""))
        )
        if cuts_without_numbers >= 3:
            warnings.append(f"FORMAT_FACT_SOFT: 수치 없는 컷 {cuts_without_numbers}개 (권장 최대 2개)")

    elif fmt_type == "MYSTERY":
        # 컷1 [SHOCK] — 권장 (warning)
        first_desc = cuts[0].get("description", cuts[0].get("text", ""))
        if "SHOCK" not in first_desc.upper():
            warnings.append("FORMAT_MYSTERY_SOFT: 컷1 [SHOCK] 태그 권장 — 미스터리 선언 강도 약할 수 있음")
        # 열린 결말 [LOOP] (뼈대 — hard fail)
        last_desc = cuts[-1].get("description", cuts[-1].get("text", ""))
        if "LOOP" not in last_desc.upper():
            failures.append("FORMAT_MYSTERY: 마지막 컷 [LOOP] 태그 없음 — 열린 결말 필수")
        # 마지막 컷 SHOCK/URGENCY 금지 (뼈대 — hard fail)
        if any(t in last_desc.upper() for t in ("SHOCK", "URGENCY")):
            failures.append("FORMAT_MYSTERY: 마지막 컷 [SHOCK/URGENCY] 금지 — 열린 결말에 부적합")
        # 가설 수 — 권장 (warning)
        tension_count = sum(
            1 for c in cuts
            if "TENSION" in (c.get("description", "") or c.get("text", "")).upper()
        )
        if tension_count < 2:
            warnings.append(f"FORMAT_MYSTERY_SOFT: 가설 {tension_count}개 (권장 2개 이상)")

    # 7) 톤-채널 일치 검증 (warning)
    if channel:
        from modules.utils.channel_config import get_channel_preset
        preset = get_channel_preset(channel)
        if preset:
            tone = preset.get("tone", "").lower()
            all_scripts = " ".join(c.get("script", "") for c in cuts).lower()
            if "energetic" in tone or "rápido" in tone or "enérgico" in tone:
                formal_patterns = ["sin embargo", "no obstante", "cabe mencionar"]
                if any(p in all_scripts for p in formal_patterns):
                    warnings.append(f"TONE_MISMATCH: LATAM 에너지 채널에 형식적 표현 사용")
            if "calm" in tone or "cinematic" in tone:
                exclaim_count = sum(1 for c in cuts if "!" in c.get("script", ""))
                if exclaim_count > len(cuts) * 0.5:
                    warnings.append(f"TONE_MISMATCH: calm 채널에 감탄부호 과다 ({exclaim_count}/{len(cuts)}컷)")

    for warning in warnings:
        print(f"⚠️ [SOFT GUARD] {warning}")

    return failures


def _validate_narrative_arc(cuts: list[dict], lang: str = "ko") -> list[str]:
    """narrative_blueprint 아크 코드 검증 — 감정 태그 기반, LLM 호출 없음.

    검증 항목:
    1. HOOK: 첫 컷 강한 감정 (SHOCK/URGENCY/DISBELIEF)
    2. LOOP: 마지막 컷 열린 마무리 감정 (SHOCK/URGENCY 끝 금지)
    3. CLIMAX: 후반부(컷5~끝-1)에 SHOCK/REVEAL/URGENCY 존재
    4. PIVOT: 중반부(컷3~5)에 REVEAL/SHOCK 존재 (두 번째 훅)
    5. RELEASE: WONDER/CALM/IDENTITY 최소 1개
    """
    _EMOTION_RE = re.compile(
        r'\[(SHOCK|WONDER|TENSION|REVEAL|URGENCY|DISBELIEF|IDENTITY|CALM|LOOP)\]', re.IGNORECASE
    )
    emotions: list[str | None] = []
    for cut in cuts:
        m = _EMOTION_RE.search(cut.get("description", "") or cut.get("text", ""))
        emotions.append(m.group(1).upper() if m else None)

    if not emotions or len(emotions) < 4:
        return []  # 컷 수 부족은 다른 검증에서 처리

    issues: list[str] = []

    # 1. HOOK: 첫 컷은 포맷별 선행 감정 필수
    fmt_type = ((cuts[0].get("format_type") or "") if cuts else "").upper()
    high_emotions = {"SHOCK", "URGENCY", "DISBELIEF"}
    if fmt_type == "EMOTIONAL_SCI":
        high_emotions = {"WONDER", "IDENTITY", "TENSION"}
    if emotions[0] not in high_emotions:
        issues.append(
            f"ARC_HOOK: 첫 컷 감정 [{emotions[0]}] 약함 — {'/'.join(sorted(high_emotions))} 필요"
        )

    # 2. LOOP: 마지막 컷은 열린 마무리 (SHOCK/URGENCY로 끝나면 루프 안 됨)
    if emotions[-1] in ("SHOCK", "URGENCY"):
        issues.append(
            f"ARC_LOOP: 마지막 컷 [{emotions[-1]}] — 루프 엔딩에 부적합. CALM/WONDER/IDENTITY 권장"
        )

    # 3. CLIMAX: 후반부(컷5~끝-1)에 임팩트 감정 존재
    climax_emotions = {"SHOCK", "REVEAL", "URGENCY", "DISBELIEF"}
    if fmt_type == "EMOTIONAL_SCI":
        climax_emotions = {"REVEAL", "WONDER", "IDENTITY", "TENSION"}
    climax_range = emotions[4:-1] if len(emotions) > 5 else emotions[3:-1]
    if climax_range and not any(e in climax_emotions for e in climax_range if e):
        issues.append(
            f"ARC_CLIMAX: 후반부 클라이맥스 없음 — 컷5~끝-1에 {'/'.join(sorted(climax_emotions))} 필요"
        )

    # 4. PIVOT: 중반부(컷3~5)에 두 번째 훅 (REVEAL or SHOCK)
    pivot_range = emotions[2:5] if len(emotions) > 4 else emotions[2:]
    pivot_emotions = {"REVEAL", "SHOCK", "DISBELIEF", "URGENCY"}
    if fmt_type == "EMOTIONAL_SCI":
        pivot_emotions = {"REVEAL", "TENSION", "IDENTITY", "WONDER"}
    if pivot_range and not any(e in pivot_emotions for e in pivot_range if e):
        issues.append(
            f"ARC_PIVOT: 중반부(컷3~5) 두 번째 훅 없음 — {'/'.join(sorted(pivot_emotions))} 필요"
        )

    # 5. RELEASE: 이완 컷 (WONDER/CALM/IDENTITY) 최소 1개
    release_emotions = {"WONDER", "CALM", "IDENTITY"}
    if not any(e in release_emotions for e in emotions if e):
        issues.append(
            "ARC_RELEASE: 이완 컷 없음 — WONDER/CALM/IDENTITY 최소 1개 필요 (파도형 리듬)"
        )

    return issues


def _validate_region_style(cuts: list[dict], channel: str | None = None) -> list[str]:
    """채널의 지역 비주얼 스타일이 image_prompt에 반영되었는지 검증."""
    if not cuts or not channel:
        return []

    from modules.utils.channel_config import get_channel_preset
    preset = get_channel_preset(channel)
    if not preset:
        return []

    warnings: list[str] = []
    visual_style = preset.get("visual_style", "").lower()
    all_prompts = " ".join(c.get("prompt", "") for c in cuts).lower()

    # US Hispanic (어두운 시네마틱) — vibrant/neon 과다 사용 감지
    if "dark background" in visual_style or "mysterious" in visual_style:
        bright_count = sum(1 for kw in ["vibrant", "neon", "colorful", "bright", "saturated"]
                          if kw in all_prompts)
        dark_count = sum(1 for kw in ["dark", "dramatic", "cinematic", "contrast", "mysterious", "shadow"]
                         if kw in all_prompts)
        if bright_count > dark_count:
            warnings.append(
                f"REGION_STYLE: 어두운 시네마틱 채널인데 밝은 키워드({bright_count}) > 어두운 키워드({dark_count})")

    # LATAM (밝고 화려) — dark/muted 과다 사용 감지
    if "vibrant" in visual_style or "colorful" in visual_style or "high saturation" in visual_style:
        dark_count = sum(1 for kw in ["dark", "muted", "desaturated", "shadow", "noir"]
                         if kw in all_prompts)
        bright_count = sum(1 for kw in ["vibrant", "neon", "colorful", "bright", "glowing", "saturated"]
                           if kw in all_prompts)
        if dark_count > bright_count:
            warnings.append(
                f"REGION_STYLE: 밝은 LATAM 채널인데 어두운 키워드({dark_count}) > 밝은 키워드({bright_count})")

    # 영어 (다큐멘터리) — neon/glowing 과다 사용 감지
    if "documentary" in visual_style or "natural" in visual_style:
        fantasy_count = sum(1 for kw in ["neon", "glowing", "fantasy", "surreal", "exaggerated"]
                            if kw in all_prompts)
        if fantasy_count > len(cuts) * 0.4:
            warnings.append(
                f"REGION_STYLE: 다큐멘터리 채널에 판타지 키워드 과다 ({fantasy_count}개)")

    return warnings
