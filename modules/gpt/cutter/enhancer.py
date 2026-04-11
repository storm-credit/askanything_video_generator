import json
from typing import Any

from .parser import _extract_json
from .llm_client import _request_gemini_freeform, _request_gemini, _request_openai_freeform, _request_claude


def _enhance_image_prompts(cuts: list[dict], topic: str, lang: str, api_key: str,
                           channel: str | None = None, format_type: str | None = None) -> list[dict]:
    """비주얼 디렉터 — image_prompt 전문 리라이트. 컷1은 스크롤 멈추기 특별 강화."""
    if not cuts or not api_key:
        return cuts

    print(f"-> [비주얼 디렉터] image_prompt 최적화 중... (포맷: {format_type or 'AUTO'})")

    # 채널별 비주얼 스타일 (channel_config.py에서 가져옴 — 데이터 일원화)
    from modules.utils.channel_config import get_channel_preset
    _preset = get_channel_preset(channel) if channel else None
    channel_style = (_preset or {}).get("visual_style", "cinematic realism, dramatic lighting")

    # 포맷별 비주얼 전략 — Cut 1 구성 방식과 전체 색감 방향 결정
    _format_visual_strategy = {
        "WHO_WINS": (
            "FORMAT=WHO_WINS: Cut 1 MUST show exact 50/50 left-right split frame with both subjects. "
            "Left subject uses COOL lighting (blue/purple), right uses WARM lighting (orange/red). "
            "Subjects face each other, frame-filling, max contrast. "
            "Cut 10 (REVEAL): winner solo, hero lighting from above, loser blurred behind."
        ),
        "IF": (
            "FORMAT=IF: Cut 1 shows catastrophic transformation — left=normal, right=extreme change "
            "OR before/after split. Color saturation escalates each cut (+20% per cut). "
            "Cut 8 (CLIMAX): near-monochrome dark OR explosively bright, fragmentation/scale extreme."
        ),
        "EMOTIONAL_SCI": (
            "FORMAT=EMOTIONAL_SCI: ALL cuts MUST use warm palette (gold/amber/coral/rose). "
            "NO dark/cold/explosive imagery. Cut 1 = everyday wonder, macro beauty, soft ethereal glow. "
            "Human scale connection in all cuts. Warm white balance throughout."
        ),
        "FACT": (
            "FORMAT=FACT: Documentary realism. Natural lighting, no oversaturation. "
            "Cut 1 = authoritative reveal, clear focal subject, professional depth. "
            "Educational clarity over visual shock. Refined, high-quality aesthetic."
        ),
        "COUNTDOWN": (
            "FORMAT=COUNTDOWN: Visual intensity increases with rank. "
            "Cut 1 = panoramic overview setting the scale. "
            "5th-2nd: progressively more dramatic lighting and scale per rank. "
            "1st place (REVEAL): maximum impact — dramatic lighting, full-frame, overwhelming presence. "
            "Final cut: mystery silhouette hinting at next TOP 5."
        ),
        "SCALE": (
            "FORMAT=SCALE: Maximize visual size contrast between objects. "
            "Cut 1 = extreme size contrast wide angle, miniature vs giant side by side. "
            "Each cut zooms out further — continuous scale expansion feeling. "
            "Hero cut: overwhelming cosmic/nature scale, awe-inspiring. "
            "Final: tiny human silhouette against massive backdrop — humility."
        ),
        "PARADOX": (
            "FORMAT=PARADOX: Color tone SHIFTS dramatically at each reversal. "
            "Cuts 1-2 = bright, pastel, stable — reassuring false comfort. "
            "Cut 3 (reversal): sudden dark dramatic shift — truth begins. "
            "Cuts 4-5 = cold blue/neon — deep truth exposed. "
            "Cut 6 = warm tone returns — personal/intimate. "
            "Final: half-and-half light/dark composition — duality."
        ),
        "MYSTERY": (
            "FORMAT=MYSTERY: Dark, atmospheric, mysterious throughout. "
            "Cut 1 = silhouette in fog/mist — unknown presence. "
            "Cut 2 = historical/antiquated location, vintage lighting. "
            "Cuts 3-4 = cold fluorescent, investigation/lab feeling. "
            "Cut 5 = darkest frame — near-horror atmosphere. "
            "Cut 6 = slight warm light — thread of hypothesis. "
            "Final: door/portal opening — gateway to next mystery."
        ),
    }.get(format_type or "", "")

    scripts_and_prompts = []
    for i, cut in enumerate(cuts):
        scripts_and_prompts.append({
            "cut": i + 1,
            "script": cut.get("script", ""),
            "current_prompt": cut.get("prompt", ""),
        })

    prompt = f"""You are a world-class visual director for viral YouTube Shorts. Your ONLY job is to rewrite image_prompts to maximize scroll-stopping power.

Topic: {topic}
Format: {format_type or 'AUTO'}
Channel style: {channel_style}
Language: {lang}

FORMAT VISUAL STRATEGY (HIGHEST PRIORITY):
{_format_visual_strategy if _format_visual_strategy else "No specific format — maximize visual impact freely."}

RULES:
- CRITICAL: Do NOT introduce ANY subject not present in the script. The main subject in each script line MUST be the main subject in the image_prompt. Adding unrelated subjects = FAIL.
- Cut 1 is the MOST IMPORTANT. It MUST stop the scroll. Include at least 2: extreme scale contrast, intense color contrast, surreal/impossible scene, eye-locking composition.
- Every image_prompt must START with the main subject from the script.
- Describe SCENES, not keywords. Full sentences produce better images.
- Each cut must use a DIFFERENT camera technique (close-up, wide shot, aerial, macro, etc.)
- 9:16 vertical composition: place subject in upper or lower 1/3, leave top 15% and bottom 20% clear for subtitles.
- Negative constraints: NO text, NO watermark, NO logo, NO diagrams, NO infographic, NO cartoon, NO anime, NO illustration.
- 40-60 words per prompt (Cut 1 may use up to 70 words).
- Output ONLY a JSON array of objects: [{{"cut": 1, "image_prompt": "..."}}, ...]

Current cuts:
{json.dumps(scripts_and_prompts, ensure_ascii=False)}

IMPORTANT — Color Continuity:
- All cuts MUST share a consistent dominant color palette (format strategy overrides this if specified).
- Space topics: deep blue-black | Prehistoric: warm amber-green | Ocean: dark teal-blue | Earth: warm earth tones

Rewrite ALL image_prompts. Make Cut 1 DRAMATICALLY (3x) more visually striking than the rest."""

    try:
        raw = _request_gemini_freeform(api_key, prompt, "gemini-2.5-flash")
        result = _extract_json(raw)

        if not isinstance(result, list):
            print(f"  [비주얼 디렉터] 응답 파싱 실패 — 원본 유지")
            return cuts

        enhanced_count = 0
        for item in result:
            if not isinstance(item, dict):
                continue
            idx = item.get("cut", 0) - 1
            new_prompt = item.get("image_prompt", "")
            if not new_prompt or not (0 <= idx < len(cuts)):
                continue

            # 길이 검증: 너무 짧거나 길면 스킵
            if len(new_prompt) < 20 or len(new_prompt) > 500:
                continue

            old_prompt = cuts[idx].get("prompt", "")
            cuts[idx]["prompt"] = new_prompt
            enhanced_count += 1

            if idx == 0:
                print(f"  [비주얼 디렉터] 컷1 image_prompt 강화 완료")

        if enhanced_count > 0:
            print(f"OK [비주얼 디렉터] {enhanced_count}개 컷 image_prompt 최적화 완료")
        else:
            print(f"  [비주얼 디렉터] 변경 없음 — 원본 유지")

    except Exception as e:
        print(f"  [비주얼 디렉터] 에러 — 원본 유지: {e}")

    return cuts


# ── 학술체 리라이트 ─────────────────────────────────────────────────

def _rewrite_academic_tone(cuts: list[dict], lang: str, llm_provider: str, api_key: str, model: str | None = None) -> list[dict]:
    """학술체 표현을 펀치력 있는 구어체로 리라이트."""
    academic_patterns = {
        "ko": ["연구에 따르면", "과학자들이 발견", "에 의하면", "것으로 밝혀", "것으로 알려져", "분석에 따르면", "논문에 따르면"],
        "en": ["according to", "studies show", "researchers found", "scientists discovered", "research suggests", "a study published"],
        "es": ["según estudios", "los científicos descubrieron", "investigaciones demuestran", "un estudio publicado"],
    }
    patterns = academic_patterns.get(lang, academic_patterns["en"])

    # 학술체가 포함된 컷만 추출
    targets = []
    for i, cut in enumerate(cuts):
        script = cut.get("script", "")
        if any(p.lower() in script.lower() for p in patterns):
            targets.append({"cut": i + 1, "script": script})

    if not targets:
        return cuts

    rewrite_rules = {
        "ko": "학술적 도입부를 제거하고 팩트를 바로 던지는 반말 구어체로 바꿔라. 의미는 유지. 예: '연구에 따르면 이 물질은 독성이 있어' → '이 물질, 금보다 독해'",
        "en": "Remove academic introductions and state the fact directly. Keep meaning. Example: 'According to NASA, this planet has diamond rain' → 'This planet rains diamonds.'",
        "es": "Elimina introducciones académicas y di el dato directamente. Mantén el significado. Ejemplo: 'Según estudios, este animal...' → 'Este animal...'",
    }

    prompt = f"""Rewrite ONLY the scripts below to remove academic/research-framing language.
Rule: {rewrite_rules.get(lang, rewrite_rules['en'])}

Scripts to fix:
{json.dumps(targets, ensure_ascii=False)}

Output JSON array: [{{"cut": 1, "script": "rewritten"}}]
ONLY output scripts that were changed. Keep same length range."""

    try:
        import json as _json
        raw = _request_gemini_freeform(api_key, prompt, model)
        rewrites = _json.loads(raw)
        if isinstance(rewrites, list):
            for rw in rewrites:
                idx = rw.get("cut", 0) - 1
                new_script = rw.get("script", "")
                if 0 <= idx < len(cuts) and new_script:
                    old = cuts[idx]["script"]
                    cuts[idx]["script"] = new_script
                    print(f"  [학술체 리라이트] Cut {idx+1}: '{old[:30]}' → '{new_script[:30]}'")
    except Exception as e:
        print(f"  [학술체 리라이트] 실패 (원본 유지): {e}")

    return cuts


# ── 문장 자연화 리라이트 (Script Polisher) ─────────────────────────


def _get_sentence_polish_prompt(lang: str, channel: str | None = None) -> str:
    """채널별 문장 다듬기 프롬프트를 반환합니다."""
    if channel == "askanything":
        return """너는 한국어 쇼츠 대본 문장 다듬기 전문가다. 친구한테 신기한 얘기 해주는 느낌으로.

핵심 원칙:
- 소리 내서 읽었을 때 자연스러워야 한다. 어색하면 실패.
- 번역투/설명체/교과서체를 전부 없앤다.
- 한국어 어순: 핵심 단어를 앞에 놓아라.

★ 자주 나오는 나쁜 패턴 → 고치는 법:
❌ "이것은 매우 독특한 특성을 가지고 있어" → ✅ "이거 진짜 특이해"
❌ "그것이 발견된 이유는 ~때문이야" → ✅ "발견된 이유? ~때문이야"
❌ "이 생물은 어둠 속에서 빛을 만들어내" → ✅ "이 생물, 어둠 속에서 스스로 빛나"
❌ "그 결과로 인해 ~하게 되었어" → ✅ "그래서 ~됐어"
❌ "이것은 ~라고 할 수 있어" → ✅ "~인 거야"
❌ "~하는 것으로 알려져 있어" → ✅ "~하거든"
❌ "이 현상은 ~에 의해 발생해" → ✅ "~가 이걸 만들어"
❌ "약 50%에 달하는 비율이야" → ✅ "절반이야"
❌ "~할 수 있는 능력을 가지고 있어" → ✅ "~할 수 있어"

★ 어미 다양성 (같은 어미 2번 연속 금지):
"~야" "~거든" "~잖아" "~거야" "~인데" "~라는 거지" "~알아?"
이 중에서 골고루 섞어 써라.

★ 리듬감:
짧은 문장(15자) → 긴 문장(30자) → 짧은 문장 교대.
3문장 연속 같은 길이 금지.

반드시 지킬 것:
- 컷 수 유지, 각 컷 한 문장
- 원래 정보 추가/삭제 금지
- "미쳤다", "레전드", "ㄹㅇ", "ㅋㅋ" 금지
- 훅은 더 세게 만들 수는 있어도 약하게 만들면 안 됨

출력: JSON만
{"rewritten_scripts": ["컷1", "컷2"], "notes": ["수정 메모"]}"""

    if channel == "wonderdrop":
        return """You are an English short-form script polisher for a science/documentary channel.

Goal:
- Keep the original meaning and factual caution.
- Rewrite each line so it sounds natural, cinematic, and spoken aloud.
- Remove stiff translation-like phrasing.
- Keep the tone calm, clear, slightly mysterious, and documentary-like.
- Avoid overhype, slang, childish delivery, or forced clickbait.

Must keep:
- Same number of cuts
- One sentence per cut
- Similar length per cut
- No new facts
- No stronger factual certainty than the original
- Keep the hook strong

Output JSON only:
{"rewritten_scripts": ["Cut 1 line", "Cut 2 line"], "notes": ["brief fix notes"]}"""

    if channel == "exploratodo":
        return """Eres un editor de guiones cortos en español para un canal energético y visualmente impactante.

Objetivo:
- Mantener el significado original.
- Hacer que cada línea suene natural, rápida y clara en español.
- Evitar frases traducidas literalmente o construcciones torpes.
- Mantener energía y sorpresa, pero sin sonar infantil ni exagerado.

Reglas:
- Mantener el mismo número de cortes
- Una sola oración por corte
- No agregar datos nuevos
- No volver más categórico algo incierto
- Mantener el gancho fuerte
- Evitar regionalismos muy marcados

Salida JSON:
{"rewritten_scripts": ["línea 1", "línea 2"], "notes": ["cambios principales"]}"""

    if channel == "prismtale":
        return """Eres un pulidor de guiones breves para un canal de tono cinematográfico, misterioso y español neutro.

Objetivo:
- Mantener exactamente la idea original.
- Reescribir cada línea para que suene natural, sobria e intrigante.
- Eliminar frases rígidas, artificiales o demasiado promocionales.
- Mantener un tono de documental breve, elegante y claro.

Debes mantener:
- mismo número de cortes
- una oración por corte
- longitud similar
- sin añadir información nueva
- sin aumentar la certeza factual
- sin volverlo juguetón o exagerado

Salida JSON:
{"rewritten_scripts": ["línea 1", "línea 2"], "notes": ["ajustes principales"]}"""

    # fallback by language
    if lang == "ko":
        return """너는 한국어 숏폼 대본 문장 교정자다. 의미는 유지하고, 더 자연스럽고 말하듯 들리게 고쳐라. 컷 수 유지, 한 컷 한 문장, 새 정보 추가 금지. JSON만 출력: {"rewritten_scripts":["문장1"],"notes":["메모"]}"""
    if lang == "es":
        return """Eres un corrector de guiones breves en español. Mantén el significado y haz que suene más natural al hablar. Mismo número de cortes, una oración por corte, sin datos nuevos. Salida JSON: {"rewritten_scripts":["línea 1"],"notes":["nota"]}"""
    return """You are a short-form script polisher. Keep the meaning, make it sound natural when spoken, keep one sentence per cut, and add no new facts. Output JSON only: {"rewritten_scripts":["line 1"],"notes":["note"]}"""


def _is_script_rewrite_safe(old: str, new: str) -> bool:
    """리라이트가 안전한지 검사 (너무 길어지거나 짧아지면 거부)."""
    old = (old or "").strip()
    new = (new or "").strip()
    if not old or not new:
        return False
    if len(new) > len(old) * 1.5:
        return False
    if len(new) < max(6, int(len(old) * 0.5)):
        return False
    return True


def polish_scripts(cuts: list[dict[str, Any]], lang: str = "ko",
                   channel: str | None = None,
                   llm_provider: str = "gemini",
                   api_key: str | None = None,
                   llm_model: str | None = None) -> tuple[list[dict[str, Any]], list[str]]:
    """생성된 컷의 script만 자연스럽게 다듬습니다. 구조/정보는 변경하지 않음."""
    if not cuts:
        return cuts, []

    system_prompt = _get_sentence_polish_prompt(lang, channel)
    payload = {"scripts": [c.get("script", "").strip() for c in cuts]}
    user_content = json.dumps(payload, ensure_ascii=False)

    try:
        if llm_provider == "gemini":
            content = _request_gemini(api_key, system_prompt, user_content, llm_model)
        elif llm_provider == "claude":
            content = _request_claude(api_key, system_prompt, user_content, llm_model)
        else:
            content = _request_openai_freeform(api_key, system_prompt, user_content, llm_model)

        if not content:
            return cuts, ["[polisher] LLM 응답 없음 — 원본 유지"]

        data = json.loads(content) if isinstance(content, str) else content
        if not isinstance(data, dict):
            return cuts, ["[polisher] JSON 파싱 실패 — 원본 유지"]

        rewritten = data.get("rewritten_scripts", [])
        notes = data.get("notes", [])

        if not isinstance(rewritten, list) or len(rewritten) != len(cuts):
            return cuts, [f"[polisher] 컷 수 불일치 ({len(rewritten)} vs {len(cuts)}) — 원본 유지"]

        # script만 교체 (안전 검사 통과한 것만), 나머지(description, image_prompt) 유지
        applied = 0
        for i, new_script in enumerate(rewritten):
            if isinstance(new_script, str) and _is_script_rewrite_safe(cuts[i].get("script", ""), new_script):
                cuts[i]["script"] = new_script.strip()
                applied += 1

        log_notes = notes if isinstance(notes, list) else []
        print(f"[polisher] 다듬기 완료: {applied}/{len(cuts)}컷 적용")
        if log_notes:
            for n in log_notes[:3]:
                print(f"  - {n}")
        return cuts, log_notes

    except Exception as e:
        print(f"[polisher] 오류 — 원본 유지: {e}")
        return cuts, [f"[polisher] 오류: {e}"]
