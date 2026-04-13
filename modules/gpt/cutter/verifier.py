from .parser import _extract_json, _sanitize_llm_input
from .llm_client import _request_gemini_freeform, _request_openai_freeform


def _get_channel_hook_profile(channel: str | None) -> str:
    """채널별 컷1 훅 성격 가이드."""
    if channel == "askanything":
        return "askanything = bold, punchy Korean curiosity hook. Strong questions allowed. Weak 'did you know' style is bad."
    if channel == "wonderdrop":
        return "wonderdrop = calm, authoritative documentary opener. Prefer declarative cinematic confidence over casual questions."
    if channel == "exploratodo":
        return "exploratodo = energetic LATAM opener. Fast, urgent, high-click energy. Formal tone is bad."
    if channel == "prismtale":
        return "prismtale = dark, mysterious declaration. Ominous and cinematic. Avoid playful or generic openers."
    return "default = short, strong, curiosity-driven opener."


def _verify_subject_match(cuts: list[dict], topic: str,
                          llm_provider: str, api_key: str, lang: str,
                          llm_model: str | None = None) -> list[dict]:
    """각 컷의 script 핵심 주어가 image_prompt에 포함되는지 검증하고, 불일치 시 LLM으로 수정."""
    if not cuts or len(cuts) < 3:
        return cuts

    # 각 컷의 script→image_prompt 주제 일치 여부를 LLM에게 한번에 검증 요청
    pairs = "\n".join(
        f"Cut {i+1}:\n  script: {c['script']}\n  image_prompt: {c['prompt']}"
        for i, c in enumerate(cuts)
    )
    verify_prompt = f"""You are a strict visual consistency checker for short-form video.

[TOPIC] {topic}

[CUTS]
{pairs}

[TASK]
For each cut, check if the image_prompt correctly depicts the MAIN SUBJECT from the script.
- "script" describes what the narrator says.
- "image_prompt" describes the visual shown on screen.
- The main subject in the image MUST match the main subject mentioned in the script.

Examples of MISMATCH:
- script talks about "sharks" but image_prompt shows "whale" → MISMATCH
- script talks about "lightning" but image_prompt shows "sunset" → MISMATCH
- script talks about "brain" but image_prompt shows "galaxy" → MISMATCH

Examples of MATCH:
- script talks about "sharks" and image_prompt shows "great white shark" → MATCH
- script mentions "deep ocean pressure" and image_prompt shows "submersible in dark ocean" → MATCH (related context is OK)

Output ONLY a JSON array. For each cut with a mismatch, include a corrected image_prompt.
Format: [{{"cut": 1, "match": true}}, {{"cut": 2, "match": false, "fixed_prompt": "corrected English image prompt that matches the script subject"}}]
Return raw JSON only, no markdown code blocks."""

    print(f"-> [주제 일치 검증] {len(cuts)}개 컷의 script↔image_prompt 일치 확인 중...")

    try:
        if llm_provider == "gemini":
            raw = _request_gemini_freeform(api_key, verify_prompt, llm_model)
        else:
            raw = _request_openai_freeform(api_key, "You are a visual consistency checker.", verify_prompt, llm_model)

        result = _extract_json(raw) or []
        if not isinstance(result, list):
            print(f"  [주제 검증] 응답 파싱 실패 — 원본 유지")
            return cuts

        fixed_count = 0
        for item in result:
            if not isinstance(item, dict):
                continue
            if item.get("match") is False and item.get("fixed_prompt"):
                idx = item.get("cut", 0) - 1
                if 0 <= idx < len(cuts):
                    old_prompt = cuts[idx]["prompt"]
                    cuts[idx]["prompt"] = item["fixed_prompt"]
                    fixed_count += 1
                    print(f"  [주제 수정] 컷{idx+1}: '{old_prompt[:40]}...' → '{item['fixed_prompt'][:40]}...'")

        if fixed_count == 0:
            print(f"OK [주제 검증] 모든 컷 script↔image_prompt 일치 확인 (수정 없음)")
        else:
            print(f"OK [주제 검증] {fixed_count}개 컷 image_prompt 주제 수정 완료")
        return cuts

    except Exception as e:
        print(f"  [주제 검증 실패] {e} — 원본 유지")
        return cuts


def _verify_highness_structure(cuts: list[dict], topic: str,
                               llm_provider: str, api_key: str, lang: str,
                               llm_model: str | None = None, channel: str | None = None) -> list[dict]:
    """하이네스 구조 검증 — 컷1(훅)과 마지막 컷(루프)만 점검 + 자동 수정.

    범위 축소 (v2.1): 중간 컷 구조는 건드리지 않음.
    - 컷1: 약한/뻔한 오프너만 교체 (강한 질문형은 허용)
    - 마지막 컷: 빈 CTA나 미완성 문장만 교체
    """
    if not cuts or len(cuts) < 5:
        return cuts

    # 채널별 루프 스타일 결정
    from modules.utils.channel_config import get_channel_preset
    preset = get_channel_preset(channel) if channel else None
    loop_style = "medium"  # 기본값
    if preset:
        tone = preset.get("tone", "")
        if "very strong" in tone or "direct" in tone.lower():
            loop_style = "strong"
        elif "natural" in tone or "subtle" in tone:
            loop_style = "subtle"

    first_script = cuts[0]["script"]
    second_script = cuts[1]["script"] if len(cuts) > 1 else ""
    second_last_script = cuts[-2]["script"] if len(cuts) > 2 else ""
    last_script = cuts[-1]["script"]
    hook_and_loop = (
        f"Cut 1: {first_script}\n"
        f"Cut 2 (context): {second_script}\n"
        f"Cut {len(cuts)-1} (context): {second_last_script}\n"
        f"Last Cut: {last_script}"
    )

    verify_prompt = f"""You are a short-form video structure expert. Review ONLY the first and last cut.

[TOPIC] {topic}
[LANGUAGE] {lang}
[LOOP STYLE] {loop_style}
[CHANNEL HOOK PROFILE] {_get_channel_hook_profile(channel)}

[CUTS TO REVIEW]
{hook_and_loop}

[CHECK THESE RULES]
1. HOOK (Cut 1): Strong opener matching the channel hook profile. Questions are ALLOWED only when they fit the channel. Weak openers are NOT.
   - ❌ "Did you know...?" / "¿Sabías que...?" / "Today we'll talk about..." / "이건 흥미롭다"
   - ✅ opener should match the channel profile above while creating immediate curiosity/impact

2. LOOP ENDING (Last cut): Must be a COMPLETE sentence with no empty CTA.
   - ❌ "Next time..." / incomplete sentence / weak 4th-wall ending
   - ✅ complete ending with thematic echo to the hook

[OUTPUT FORMAT]
Return a JSON object:
{{
  "hook_ok": true/false,
  "hook_issue": "description if not ok, null if ok",
  "loop_ok": true/false,
  "loop_issue": "description if not ok, null if ok",
  "fixes": [
    {{"cut": 1, "field": "script", "original": "...", "fixed": "corrected version"}},
    {{"cut": {len(cuts)}, "field": "script", "original": "...", "fixed": "corrected version"}}
  ]
}}
Only include items in "fixes" if something needs to change. Return raw JSON only."""

    print(f"-> [하이네스 구조 검증] 컷1/마지막 컷 경량 확인 중...")

    try:
        if llm_provider == "gemini":
            raw = _request_gemini_freeform(api_key, verify_prompt, llm_model)
        else:
            raw = _request_openai_freeform(api_key, "You are a video structure expert.", verify_prompt, llm_model)

        result = _extract_json(raw) or {}
        if not isinstance(result, dict):
            print(f"  [구조 검증] 응답 파싱 실패 — 원본 유지")
            return cuts

        # 결과 로그
        issues = []
        if not result.get("hook_ok", True):
            issues.append(f"Hook: {result.get('hook_issue', 'unknown')}")
        if not result.get("loop_ok", True):
            issues.append(f"Loop: {result.get('loop_issue', 'unknown')}")

        if issues:
            print(f"  [구조 검증] 문제 발견: {' | '.join(issues)}")
        else:
            print(f"OK [구조 검증] 훅✓ 루프✓")
            return cuts

        # 수정 적용 — 컷1과 마지막 컷만 허용
        fixes = result.get("fixes", [])
        fixed_count = 0
        last_idx = len(cuts) - 1
        for fix in fixes:
            if not isinstance(fix, dict):
                continue
            idx = fix.get("cut", 0) - 1
            field = fix.get("field", "script")
            new_val = fix.get("fixed")
            if not new_val or not (0 <= idx < len(cuts)):
                continue
            # 중간 컷 수정 거부 — 컷1과 마지막 컷만 허용
            if idx != 0 and idx != last_idx:
                print(f"  [구조 수정 거부] 컷{idx+1} — 중간 컷 수정 불가 (컷1/마지막만)")
                continue

            if field != "script" or new_val == cuts[idx].get("script"):
                continue
            old = cuts[idx].get("script", "")
            if not old:
                continue
            if len(new_val) < max(10, int(len(old) * 0.6)):
                print(f"  [구조 수정 거부] 컷{idx+1} 지나치게 짧아짐 — 원본 유지")
                continue
            cuts[idx]["script"] = new_val
            fixed_count += 1
            print(f"  [구조 수정] 컷{idx+1}: '{old[:30]}...' → '{new_val[:30]}...'")


        if fixed_count == 0 and issues:
            print(f"  [구조 검증] 문제 감지되었지만 자동 수정 없음 — 원본 유지")
        elif fixed_count > 0:
            print(f"OK [구조 검증] {fixed_count}개 컷 수정 완료")

        return cuts

    except Exception as e:
        print(f"  [구조 검증 실패] {e} — 원본 유지")
        return cuts


def _verify_facts(cuts: list[dict], fact_context: str, topic: str,
                  llm_provider: str, api_key: str, lang: str, llm_model: str | None = None) -> list[dict]:
    """생성된 스크립트의 팩트를 검증하고, 틀린 부분을 수정합니다."""
    scripts = "\n".join(f"컷{i+1}: {c['script']}" for i, c in enumerate(cuts))

    safe_facts = _sanitize_llm_input(fact_context, max_len=1500)
    verify_prompt = f"""You are a strict fact-checker. Verify each script line against the provided facts.

[FACTS from search]
{safe_facts}

[GENERATED SCRIPTS]
{scripts}

[TASK]
1. Check each script line for factual accuracy.
2. If a line contains false or unverifiable information, rewrite it with correct facts.
3. If a line is accurate, keep it unchanged.
4. Maintain the same tone, style, and approximate length.

Output ONLY a JSON array of objects: [{{"cut": 1, "original": "...", "verified": "...", "changed": true/false, "reason": "..."}}]
Do NOT include markdown code blocks. Return raw JSON only."""

    print(f"-> [팩트 검증] 생성된 {len(cuts)}개 스크립트 검증 중...")

    try:
        if llm_provider == "gemini":
            raw = _request_gemini_freeform(api_key, verify_prompt, llm_model)
        else:
            raw = _request_openai_freeform(api_key, "You are a fact-checker.", verify_prompt, llm_model)

        result = _extract_json(raw) or []
        if not isinstance(result, list):
            print(f"  [팩트 검증] 응답 파싱 실패 — 원본 유지")
            return cuts

        changed_count = 0
        for item in result:
            if not isinstance(item, dict) or not item.get("changed"):
                continue
            idx = item.get("cut", 0) - 1
            if 0 <= idx < len(cuts) and item.get("verified"):
                old_script = cuts[idx]["script"]
                new_script = item["verified"]
                # 글자수 보호: 수정 후 40%+ 줄어들면 거부
                if len(new_script) < len(old_script) * 0.6:
                    print(f"  [팩트 수정 거부] 컷{idx+1} 글자수 40%+ 감소 ({len(old_script)}→{len(new_script)}) — 원본 유지")
                    continue
                if len(new_script) < 15:
                    print(f"  [팩트 수정 거부] 컷{idx+1} 15자 미만 ({len(new_script)}자) — 원본 유지")
                    continue
                cuts[idx]["script"] = new_script
                changed_count += 1
                print(f"  [팩트 수정] 컷{idx+1}: '{old_script[:30]}...' → '{new_script[:30]}...' ({item.get('reason', '')})")

        if changed_count == 0:
            print(f"OK [팩트 검증] 모든 스크립트 팩트 확인 완료 (수정 없음)")
        else:
            print(f"OK [팩트 검증] {changed_count}개 스크립트 팩트 수정 완료")
        return cuts

    except Exception as e:
        print(f"  [팩트 검증 실패] {e} — 원본 유지")
        return cuts
