from .parser import _extract_json, _sanitize_llm_input
from .llm_client import _request_gemini_freeform, _request_openai_freeform


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
    """하이네스 구조(Hook→충격체인→루프엔딩) 검증 + 자동 수정.

    검증 항목:
    1. Cut 1 = Hook: 단정문인지 (질문형 금지)
    2. Cut 4-5 = 두 번째 훅 존재 여부
    3. 마지막 Cut = 루프 엔딩: 완결 문장 + Cut 1과 연결
    4. 감정 태그 분포: 최소 3종류 이상
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
    last_script = cuts[-1]["script"]
    all_scripts = "\n".join(f"Cut {i+1}: {c['script']}" for i, c in enumerate(cuts))

    # 감정 태그 분포 확인
    emotions = []
    for c in cuts:
        desc = c.get("text", "") or c.get("description", "")
        for tag in ["SHOCK", "WONDER", "TENSION", "REVEAL", "URGENCY", "DISBELIEF", "IDENTITY"]:
            if tag in desc:
                emotions.append(tag)
                break

    emotion_variety = len(set(emotions))

    verify_prompt = f"""You are a short-form video structure expert. Check this video's "Highness Structure" (Hook → Shock Chain → Loop Ending).

[TOPIC] {topic}
[LANGUAGE] {lang}
[LOOP STYLE] {loop_style} (strong=obvious repetition, medium=clear connection, subtle=natural flow)

[ALL CUTS]
{all_scripts}

[FIRST CUT] {first_script}
[LAST CUT] {last_script}
[EMOTION TAGS FOUND] {emotion_variety} types out of 5 (need at least 3)

[CHECK THESE RULES]
1. HOOK (Cut 1): Must be a declarative statement, NOT a question. Must break common belief or present an impossible-sounding fact.
   - ❌ "Did you know...?" / "¿Sabías que...?" / "~일까?" / "Today we'll talk about..."
   - ❌ Weak/generic openers like "This is interesting" or "이건 흥미롭다"
   - ✅ "Lightning is hotter than the sun." / "Esto no debería existir." / "이건 존재해선 안 되는 거야"

2. SECOND HOOK / RETENTION LOCK (Cut 3-5): Must introduce a NEW surprising fact (not continuation of cuts 2-3). This counters the mid-video retention drop. The viewer must think "wait, WHAT?"

3. LOOP ENDING (Last cut): Must be a COMPLETE sentence. Must connect back to Cut 1.
   - If loop_style="strong": Last line should nearly mirror Cut 1
   - If loop_style="medium": Clear thematic connection to Cut 1
   - If loop_style="subtle": Natural flow back to Cut 1's topic
   - ❌ FORBIDDEN: "Next time...", incomplete sentences, weak reflective endings, 4th-wall breaking

4. EMOTION ARC: At least 3 different emotion types should be present across cuts.

[OUTPUT FORMAT]
Return a JSON object:
{{
  "hook_ok": true/false,
  "hook_issue": "description if not ok, null if ok",
  "second_hook_ok": true/false,
  "second_hook_issue": "description if not ok, null if ok",
  "loop_ok": true/false,
  "loop_issue": "description if not ok, null if ok",
  "emotion_ok": true/false,
  "fixes": [
    {{"cut": 1, "field": "script", "original": "...", "fixed": "corrected version"}},
    {{"cut": 10, "field": "script", "original": "...", "fixed": "corrected version"}}
  ]
}}
Only include items in "fixes" if something needs to change. If everything is OK, return empty fixes array.
Return raw JSON only, no markdown code blocks."""

    print(f"-> [하이네스 구조 검증] Hook/충격체인/루프엔딩/감정아크 확인 중...")

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
        if not result.get("hook_ok"):
            issues.append(f"Hook: {result.get('hook_issue', 'unknown')}")
        if not result.get("second_hook_ok"):
            issues.append(f"2nd Hook: {result.get('second_hook_issue', 'unknown')}")
        if not result.get("loop_ok"):
            issues.append(f"Loop: {result.get('loop_issue', 'unknown')}")
        if not result.get("emotion_ok"):
            issues.append("Emotion: 감정 태그 다양성 부족")

        if issues:
            print(f"  [구조 검증] 문제 발견: {' | '.join(issues)}")
        else:
            print(f"OK [구조 검증] 하이네스 구조 완벽 (Hook✓ 2nd Hook✓ Loop✓ Emotion✓)")
            return cuts

        # 수정 적용
        fixes = result.get("fixes", [])
        fixed_count = 0
        for fix in fixes:
            if not isinstance(fix, dict):
                continue
            idx = fix.get("cut", 0) - 1
            field = fix.get("field", "script")
            new_val = fix.get("fixed")
            if not new_val or not (0 <= idx < len(cuts)):
                continue

            # script 또는 description 수정 (글자수 보호: 수정 후 더 짧아지면 거부)
            if field == "script" and new_val != cuts[idx].get("script"):
                old = cuts[idx]["script"]
                # 한국어: 수정 후 20자 미만이면 거부, 영어/스페인어: 8단어 미만이면 거부
                if len(new_val) < len(old) * 0.6:
                    print(f"  [구조 수정 거부] 컷{idx+1} 글자수 40%+ 감소 ({len(old)}→{len(new_val)}) — 원본 유지")
                    continue
                if len(new_val) < 15:
                    print(f"  [구조 수정 거부] 컷{idx+1} 수정 후 15자 미만 ({len(new_val)}자) — 원본 유지")
                    continue
                cuts[idx]["script"] = new_val
                fixed_count += 1
                print(f"  [구조 수정] 컷{idx+1} script: '{old[:30]}...' → '{new_val[:30]}...'")
            elif field == "description" and new_val != cuts[idx].get("text"):
                cuts[idx]["text"] = new_val
                cuts[idx]["description"] = new_val
                fixed_count += 1
                print(f"  [구조 수정] 컷{idx+1} description 수정")

        if fixed_count == 0 and issues:
            print(f"  [구조 검증] 문제 감지되었지만 자동 수정 없음 — 원본 유지")
        elif fixed_count > 0:
            print(f"OK [구조 검증] {fixed_count}개 컷 하이네스 구조 수정 완료")

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
