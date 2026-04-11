import re
from .parser import _VALID_EMOTIONS


# ── HARD FAIL 검증 (코드 레벨 품질 게이트) ──────────────────────────

def _validate_hard_fail(cuts: list[dict], channel: str | None = None) -> list[str]:
    """프롬프트의 HARD FAIL 조건을 코드로 검증. 실패 항목 리스트 반환 (빈 리스트 = 통과)."""
    if not cuts or len(cuts) < 3:
        return []

    failures: list[str] = []

    # 1) Hook 검증 — 첫 컷이 질문형이거나 너무 약한지
    first_script = cuts[0].get("script", "")
    weak_hook_patterns = [
        "did you know", "sabías que", "알고 있", "오늘 소개",
        "today we", "have you ever", "¿sabías", "한번 알아",
        "let me tell", "들어봤", "이번에는",
    ]
    if any(p in first_script.lower() for p in weak_hook_patterns):
        failures.append(f"HOOK_WEAK: 첫 컷이 약한 패턴 포함 — '{first_script[:50]}'")
    if first_script.rstrip().endswith("?") or first_script.rstrip().endswith("？"):
        failures.append(f"HOOK_QUESTION: 첫 컷이 질문형 — '{first_script[:50]}'")

    # 1-b) Hook 길이 강제 — 채널별 Cut1 글자/단어 수 제한
    if channel:
        from modules.utils.channel_config import get_channel_preset as _get_hook_preset
        _hook_preset = _get_hook_preset(channel)
        _hook_lang = (_hook_preset or {}).get("language", "en")
        if _hook_lang == "ko":
            # 한국어: 20자 초과 시 reject (WHO_WINS/IF 등 포맷 프롬프트 20자 기준)
            if len(first_script.replace(" ", "")) > 20:
                failures.append(f"HOOK_TOO_LONG: KO 훅 {len(first_script.replace(' ', ''))}자 (최대 20자) — '{first_script[:30]}'")
        elif _hook_lang == "en":
            # 영어: 10단어 초과 시 reject
            word_count = len(first_script.split())
            if word_count > 10:
                failures.append(f"HOOK_TOO_LONG: EN 훅 {word_count}단어 (최대 10) — '{first_script[:40]}'")
        elif _hook_lang == "es":
            # 스페인어: 12단어 초과 시 reject
            word_count = len(first_script.split())
            if word_count > 12:
                failures.append(f"HOOK_TOO_LONG: ES 훅 {word_count}단어 (최대 12) — '{first_script[:40]}'")

    # 2) 긴장 상승 검증 — 감정 태그 다양성
    emotions: list[tuple[int, str]] = []  # (컷 인덱스, 태그)
    for ci, c in enumerate(cuts):
        desc = c.get("text", "") or c.get("description", "")
        for tag in ["SHOCK", "WONDER", "TENSION", "REVEAL", "URGENCY", "DISBELIEF", "IDENTITY", "LOOP", "CALM"]:
            if tag in desc.upper():
                emotions.append((ci, tag))
                break
    unique_tags = {t for _, t in emotions}
    if len(unique_tags) < 3:
        failures.append(f"TENSION_FLAT: 감정 태그 {len(unique_tags)}종류 (최소 3 필요)")
    # 2연속 동일 감정 태그 체크 (실제 컷 번호 사용)
    for i in range(1, len(emotions)):
        if emotions[i][1] == emotions[i-1][1]:
            failures.append(f"EMOTION_REPEAT: 컷 {emotions[i-1][0]+1}~{emotions[i][0]+1} 동일 태그 [{emotions[i][1]}] 연속")

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
    if fmt_type and fmt_type != "EMOTIONAL_SCI":
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

    # 7) 포맷별 구조 검증 (format_type은 line 71에서 이미 추출됨)

    if fmt_type == "WHO_WINS":
        # 컷1 반드시 [SHOCK]
        first_desc = cuts[0].get("description", cuts[0].get("text", ""))
        if "SHOCK" not in first_desc.upper():
            failures.append("FORMAT_WHO_WINS: 컷1 [SHOCK] 태그 없음 — 대결 선언 컷 필수")
        # 11컷 필수
        if len(cuts) != 11:
            failures.append(f"FORMAT_WHO_WINS: {len(cuts)}컷 → 반드시 11컷 필요 (A소개2+B소개2+대결3+과학1+승자1+루프1+훅1)")
        # REVEAL이 컷9 이후에 있어야 함 (너무 일찍 승자 공개 방지)
        for ci, c in enumerate(cuts[:min(8, len(cuts))]):
            desc = c.get("description", c.get("text", ""))
            if "REVEAL" in desc.upper():
                failures.append(f"FORMAT_WHO_WINS: 컷{ci+1} 조기 [REVEAL] — 승자는 컷9 이후 공개 필요")
                break

    elif fmt_type == "EMOTIONAL_SCI":
        # 컷1 [WONDER] 필수
        first_desc = cuts[0].get("description", cuts[0].get("text", ""))
        if "WONDER" not in first_desc.upper():
            failures.append("FORMAT_EMOTIONAL_SCI: 컷1 [WONDER] 태그 필수 — 감성과학은 경이감으로 시작")
        # 전체 컷에서 [SHOCK] 금지
        for ci, c in enumerate(cuts):
            desc = c.get("description", "") or c.get("text", "")
            if "SHOCK" in desc.upper():
                failures.append(f"FORMAT_EMOTIONAL_SCI: 컷{ci+1} [SHOCK] 금지 — 감성과학 포맷은 SHOCK 사용 불가")
        # [WONDER] 또는 [IDENTITY] 최소 2컷 이상
        warm_count = sum(
            1 for c in cuts
            if any(t in (c.get("description", "") or c.get("text", "")).upper()
                   for t in ("WONDER", "IDENTITY"))
        )
        if warm_count < 2:
            failures.append(f"FORMAT_EMOTIONAL_SCI: WONDER/IDENTITY 태그 {warm_count}컷 (최소 2 필요)")

    elif fmt_type == "IF":
        # 컷1 반드시 [SHOCK]
        first_desc = cuts[0].get("description", cuts[0].get("text", ""))
        if "SHOCK" not in first_desc.upper():
            failures.append("FORMAT_IF: 컷1 [SHOCK] 태그 없음 — 가정 선언 컷 필수")
        # 연쇄 결과 컷 최소 2개 (CHAIN/ESCALATE/BUILD 태그)
        chain_tags = {"CHAIN", "ESCALATE", "BUILD"}
        chain_count = sum(
            1 for c in cuts
            if any(t in (c.get("description", "") or c.get("text", "")).upper() for t in chain_tags)
        )
        if chain_count < 2:
            failures.append(f"FORMAT_IF: 연쇄 결과 컷 {chain_count}개 (최소 2개 CHAIN/ESCALATE 필요)")

    elif fmt_type == "COUNTDOWN":
        # 컷1 [SHOCK] 필수
        first_desc = cuts[0].get("description", cuts[0].get("text", ""))
        if "SHOCK" not in first_desc.upper():
            failures.append("FORMAT_COUNTDOWN: 컷1 [SHOCK] 태그 없음 — TOP N 선언 컷 필수")
        # [REVEAL] 태그 존재 확인 (1위 공개)
        has_reveal = any("REVEAL" in (c.get("description", "") or c.get("text", "")).upper() for c in cuts)
        if not has_reveal:
            failures.append("FORMAT_COUNTDOWN: [REVEAL] 태그 없음 — 1위 공개 컷 필수")
        # 순위 숫자 존재 검증 — 스크립트에 숫자가 최소 3개 컷에 있어야 (5위~1위)
        import re as _re
        cuts_with_numbers = sum(
            1 for c in cuts
            if _re.search(r'\d+\s*(?:위|등|번째|th|st|nd|rd|°|lugar|er[oa]?|t[oa]s?)', c.get("script", ""), _re.IGNORECASE)
        )
        if cuts_with_numbers < 3:
            failures.append(f"FORMAT_COUNTDOWN: 순위 표기 {cuts_with_numbers}컷 (최소 3컷 이상 순위 숫자 필요)")

    elif fmt_type == "SCALE":
        # 컷1 [SHOCK] 필수
        first_desc = cuts[0].get("description", cuts[0].get("text", ""))
        if "SHOCK" not in first_desc.upper():
            failures.append("FORMAT_SCALE: 컷1 [SHOCK] 태그 없음 — 스케일 충격 선언 필수")

    elif fmt_type == "PARADOX":
        # 컷1 [SHOCK] 필수
        first_desc = cuts[0].get("description", cuts[0].get("text", ""))
        if "SHOCK" not in first_desc.upper():
            failures.append("FORMAT_PARADOX: 컷1 [SHOCK] 태그 없음 — 통념 충격 선언 필수")
        # 최소 2개 반전: TENSION + REVEAL 또는 DISBELIEF 필수
        reversal_count = sum(
            1 for c in cuts
            if any(t in (c.get("description", "") or c.get("text", "")).upper()
                   for t in ("REVEAL", "DISBELIEF"))
        )
        if reversal_count < 2:
            failures.append(f"FORMAT_PARADOX: 반전 {reversal_count}개 (최소 2단계 반전 필수)")

    elif fmt_type == "FACT":
        has_reveal = any("REVEAL" in (c.get("description", "") or c.get("text", "")).upper() for c in cuts)
        if not has_reveal:
            failures.append("FORMAT_FACT: [REVEAL] 태그 없음 — 핵심 사실 공개 컷 필수")
        # 수치/통계 밀도 검증 — 수치 없는 컷 3개 이상 → FAIL
        import re as _re
        cuts_without_numbers = sum(
            1 for c in cuts
            if not _re.search(r'\d', c.get("script", ""))
        )
        if cuts_without_numbers >= 3:
            failures.append(f"FORMAT_FACT: 수치 없는 컷 {cuts_without_numbers}개 (최대 2개 허용)")

    elif fmt_type == "MYSTERY":
        # 컷1 [SHOCK] 필수
        first_desc = cuts[0].get("description", cuts[0].get("text", ""))
        if "SHOCK" not in first_desc.upper():
            failures.append("FORMAT_MYSTERY: 컷1 [SHOCK] 태그 없음 — 미스터리 선언 필수")
        # 열린 결말: 마지막 컷이 단정적이면 안 됨 — [LOOP] 필수
        last_desc = cuts[-1].get("description", cuts[-1].get("text", ""))
        if "LOOP" not in last_desc.upper():
            failures.append("FORMAT_MYSTERY: 마지막 컷 [LOOP] 태그 없음 — 열린 결말 필수")
        # 마지막 컷 SHOCK/URGENCY 금지 — 열린 결말에 부적합
        if any(t in last_desc.upper() for t in ("SHOCK", "URGENCY")):
            failures.append("FORMAT_MYSTERY: 마지막 컷 [SHOCK/URGENCY] 금지 — 열린 결말에 부적합")
        # 가설/이론 최소 2개 — [TENSION] 태그 2개 이상 필요
        tension_count = sum(
            1 for c in cuts
            if "TENSION" in (c.get("description", "") or c.get("text", "")).upper()
        )
        if tension_count < 2:
            failures.append(f"FORMAT_MYSTERY: 가설 {tension_count}개 (이론/가설 최소 2개 필요 — [TENSION] 컷)")

    # 7) 톤-채널 일치 검증
    if channel:
        from modules.utils.channel_config import get_channel_preset
        preset = get_channel_preset(channel)
        if preset:
            tone = preset.get("tone", "").lower()
            all_scripts = " ".join(c.get("script", "") for c in cuts).lower()
            # LATAM 채널인데 너무 형식적인 톤
            if "energetic" in tone or "rápido" in tone or "enérgico" in tone:
                formal_patterns = ["sin embargo", "no obstante", "cabe mencionar"]
                if any(p in all_scripts for p in formal_patterns):
                    failures.append(f"TONE_MISMATCH: LATAM 에너지 채널에 형식적 표현 사용")
            # 영어 채널인데 과도한 감탄
            if "calm" in tone or "cinematic" in tone:
                exclaim_count = sum(1 for c in cuts if "!" in c.get("script", ""))
                if exclaim_count > len(cuts) * 0.5:
                    failures.append(f"TONE_MISMATCH: calm 채널에 감탄부호 과다 ({exclaim_count}/{len(cuts)}컷)")

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
        r'\[(SHOCK|WONDER|TENSION|REVEAL|URGENCY|DISBELIEF|IDENTITY|CALM)\]', re.IGNORECASE
    )
    emotions: list[str | None] = []
    for cut in cuts:
        m = _EMOTION_RE.search(cut.get("description", "") or cut.get("text", ""))
        emotions.append(m.group(1).upper() if m else None)

    if not emotions or len(emotions) < 4:
        return []  # 컷 수 부족은 다른 검증에서 처리

    issues: list[str] = []

    # 1. HOOK: 첫 컷은 강한 감정 필수
    high_emotions = {"SHOCK", "URGENCY", "DISBELIEF"}
    if emotions[0] not in high_emotions:
        issues.append(
            f"ARC_HOOK: 첫 컷 감정 [{emotions[0]}] 약함 — SHOCK/URGENCY/DISBELIEF 필요"
        )

    # 2. LOOP: 마지막 컷은 열린 마무리 (SHOCK/URGENCY로 끝나면 루프 안 됨)
    if emotions[-1] in ("SHOCK", "URGENCY"):
        issues.append(
            f"ARC_LOOP: 마지막 컷 [{emotions[-1]}] — 루프 엔딩에 부적합. CALM/WONDER/IDENTITY 권장"
        )

    # 3. CLIMAX: 후반부(컷5~끝-1)에 임팩트 감정 존재
    climax_emotions = {"SHOCK", "REVEAL", "URGENCY", "DISBELIEF"}
    climax_range = emotions[4:-1] if len(emotions) > 5 else emotions[3:-1]
    if climax_range and not any(e in climax_emotions for e in climax_range if e):
        issues.append(
            "ARC_CLIMAX: 후반부 클라이맥스 없음 — 컷5~끝-1에 SHOCK/REVEAL/URGENCY 필요"
        )

    # 4. PIVOT: 중반부(컷3~5)에 두 번째 훅 (REVEAL or SHOCK)
    pivot_range = emotions[2:5] if len(emotions) > 4 else emotions[2:]
    pivot_emotions = {"REVEAL", "SHOCK", "DISBELIEF", "URGENCY"}
    if pivot_range and not any(e in pivot_emotions for e in pivot_range if e):
        issues.append(
            "ARC_PIVOT: 중반부(컷3~5) 두 번째 훅 없음 — REVEAL/SHOCK/URGENCY 필요"
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
