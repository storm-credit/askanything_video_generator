"""FACT 포맷 — 조사 내러티브 + 다큐멘터리 비주얼."""

FRAGMENT: dict[str, str] = {
    "ko": """

[포맷: FACT 조사 내러티브 — 반드시 준수]
이 영상은 "숨겨진 사실을 파헤치는 조사관"의 구조다.

컷 구조 (8~10컷):
- 컷1  [SHOCK]:   가장 충격적인 팩트 단도직입. 숫자/규모/시간 포함 필수.
                  "아무도 모르는 X의 진실" 구조 — 질문형 절대 금지
- 컷2  [WONDER]:  배경 세계관 설정 — 왜 이게 존재하는가
- 컷3  [TENSION]: 반전 조건 — "근데 진짜 놀라운 건"
- 컷4~7           연쇄 팩트 공개 — 각 컷이 이전 컷보다 더 충격적 (escalation)
- 컷N-1 [REVEAL]: 핵심 결론 — 단호하게 한 문장
- 컷N  [LOOP]:    "이것만큼 충격적인 게 또 있어" / 궁금증 점화형 루프

문장 규칙:
- 각 컷 1문장, 20~35자 (KO 기준)
- 수치/통계/고유명사 최소 1개/컷 포함
- "~입니다", "~합니다" 체 금지 — 구어체 단정문 유지

이미지 프롬프트 규칙:
- 모든 컷: 자연광 또는 인공조명 고급스럽게. 과포화 금지. 진지한 색감.
- 컷1: 권위 있는 주제 단독 클로즈업, 명확한 초점, 극적 조명, 신뢰감 있는 구성
- 중간 컷: 교육적 명확성, 자연스러운 스케일, 다큐멘터리 미학 유지
- 마지막 컷: 결론적 우아함, 여운 있는 단색 또는 고급 팔레트

HARD FAIL:
✗ 컷1이 질문으로 시작 → 실패
✗ 수치 없는 컷 3개 이상 → 실패
✗ escalation 없음 (컷4가 컷3보다 약하면) → 실패
""",

    "en": """

[FORMAT: FACT Investigation Narrative — STRICTLY FOLLOW]
This video is structured as an "investigator uncovering hidden truths."

Cut structure (8~10 cuts):
- Cut 1  [SHOCK]:   The most shocking fact, point-blank. MUST include number/scale/timeframe.
                    "The truth nobody talks about X" — NO questions
- Cut 2  [WONDER]:  World-building — why does this exist
- Cut 3  [TENSION]: The twist condition — "But here's the real bombshell"
- Cut 4~7           Sequential fact reveals — each cut MORE shocking than the last (escalation)
- Cut N-1 [REVEAL]: Core conclusion — one definitive sentence
- Cut N  [LOOP]:    "There's something just as shocking..." / curiosity ignition loop

Script rules:
- 1 sentence per cut, 12~18 words (EN)
- Minimum 1 statistic/proper noun/measurement per cut
- No passive voice — active declarative only

Image prompt rules:
- All cuts: Natural or refined artificial lighting. No oversaturation. Serious tone.
- Cut 1: Authoritative subject solo close-up, sharp focus, dramatic lighting, trustworthy composition
- Middle cuts: Educational clarity, natural scale, documentary aesthetic
- Final cut: Conclusive elegance, muted or refined color palette with lingering mood

HARD FAIL:
✗ Cut 1 starts with a question → FAIL
✗ 3+ cuts without statistics → FAIL
✗ No escalation (cut 4 weaker than cut 3) → FAIL
""",

    "es": """

[FORMATO: FACT Narrativa de Investigación — SEGUIR ESTRICTAMENTE]
Este video es una estructura de "investigador descubriendo verdades ocultas."

Estructura de cortes (8~10 cortes):
- Corte 1  [SHOCK]:   El hecho más impactante, directo al grano. DEBE incluir número/escala.
                      "La verdad que nadie habla sobre X" — SIN preguntas
- Corte 2  [WONDER]:  Construcción del mundo — por qué existe esto
- Corte 3  [TENSION]: El giro — "Pero aquí está lo más impresionante"
- Cortes 4~7          Revelaciones secuenciales — cada corte MÁS impactante (escalada)
- Corte N-1 [REVEAL]: Conclusión central — una oración definitiva
- Corte N  [LOOP]:    "Hay algo igual de impactante..." / loop de curiosidad

Reglas de script:
- 1 oración por corte, 10~18 palabras
- Mínimo 1 estadística/nombre propio por corte
- Sin voz pasiva — declarativo activo únicamente

Reglas de image_prompt:
- Todos los cortes: Iluminación natural o artificial refinada. Sin sobresaturación.
- Corte 1: Sujeto autoritativo en primer plano, enfoque nítido, iluminación dramática
- Cortes medios: Claridad educativa, escala natural, estética documental
- Corte final: Elegancia conclusiva, paleta de colores sobria

HARD FAIL:
✗ Corte 1 empieza con pregunta → FALLO
✗ 3+ cortes sin estadísticas → FALLO
✗ Sin escalada → FALLO
""",
}
