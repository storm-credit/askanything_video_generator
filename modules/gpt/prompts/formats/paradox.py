"""PARADOX 포맷 — 역설/반전 인지 충격 내러티브."""

FRAGMENT: dict[str, str] = {
    "ko": """

[포맷: PARADOX 역설 반전 — 반드시 준수]
이 영상은 "당연하다고 생각한 것을 뒤집는" 구조다. 패턴 인터럽트가 핵심.

컷 구조 (7~8컷):
- 컷1  [SHOCK]:   통념 충격 — "우리가 완전히 잘못 알고 있는 X" 질문형 금지.
- 컷2  [WONDER]:  일반 상식 제시 — "모두가 이렇게 알고 있다"
- 컷3  [TENSION]: 반전 1 — "하지만 실제로는 반대다." 구체적 근거 포함.
- 컷4  [DISBELIEF]: 과학적/역사적 근거 — 왜 우리가 틀렸는지 설명
- 컷5  [REVEAL]:  반전 2 (더 깊은) — "그런데 사실 이것도 틀렸다." 이중 반전.
- 컷6  [IDENTITY]: 개인 적용 — "당신 인생에서도 이게 일어나고 있다"
- 컷7  [LOOP]:    "또 다른 반전이 있는데..." → 다음 역설 암시

문장 규칙:
- 각 컷 1문장, 15~28자
- 반전 포인트에서 "하지만/그런데/실제로는" 연결어 사용
- 근거(연구, 논문, 기관) 최소 1회 인용
- 구어체 단정문 — "~입니다" 금지

이미지 프롬프트 규칙:
- 반전 포인트마다 색감/톤이 급변해야 함
- 컷1~2: 밝고 안정적 — 파스텔/자연광 (안심시키기)
- 컷3: 급변 — 어둡고 극적인 조명 (반전 시작)
- 컷4~5: 더 어두운 톤 — 네온/차가운 블루 (진실 노출)
- 컷6: 따뜻한 톤 복귀 — 개인적, 친밀한 조명
- 마지막: 반반 구도 — 밝은면/어두운면 대비 (양면성)

HARD FAIL:
✗ 반전이 1개 이하 → 실패 (최소 2단계 반전 필수)
✗ 근거/출처 없이 주장만 → 실패
✗ 색감 변화 지시 없는 image_prompt → 실패
""",

    "en": """

[FORMAT: PARADOX Reversal — STRICTLY FOLLOW]
This video "flips what you thought was obvious." Pattern interrupt is the core.

Cut structure (7~8 cuts):
- Cut 1  [SHOCK]:   Challenge common belief — "Everything you know about X is wrong." NO questions.
- Cut 2  [WONDER]:  Present conventional wisdom — "Everyone believes this"
- Cut 3  [TENSION]: Reversal 1 — "But the reality is the opposite." Include specific evidence.
- Cut 4  [DISBELIEF]: Scientific/historical proof — why we were wrong
- Cut 5  [REVEAL]:  Reversal 2 (deeper) — "But even THAT is wrong." Double twist.
- Cut 6  [IDENTITY]: Personal application — "This is happening in YOUR life right now"
- Cut 7  [LOOP]:    "There's another twist..." → hint at next paradox

Script rules:
- 1 sentence per cut, 8~14 words
- Use transition words at reversal points: "But/However/Actually"
- Minimum 1 study/paper/institution citation
- Active declarative only

Image prompt rules:
- Color tone MUST shift dramatically at each reversal point
- Cuts 1-2: Bright and stable — pastel/natural light (reassuring)
- Cut 3: Sudden shift — dark, dramatic lighting (reversal begins)
- Cuts 4-5: Darker tone — neon/cold blue (truth exposed)
- Cut 6: Warm tone returns — personal, intimate lighting
- Final: Half-and-half composition — bright/dark contrast (duality)

HARD FAIL:
✗ Fewer than 2 reversals → FAIL
✗ Claims without evidence/source → FAIL
✗ Image prompts without color shift instructions → FAIL
""",

    "es": """

[FORMATO: PARADOX Reversión — SEGUIR ESTRICTAMENTE]
Este video "voltea lo que creías obvio." La interrupción de patrón es el núcleo.

Estructura de cortes (7~8 cortes):
- Corte 1  [SHOCK]:   Desafiar creencia común — "Todo lo que sabes sobre X está mal." SIN preguntas.
- Corte 2  [WONDER]:  Presentar sabiduría convencional — "Todos creen esto"
- Corte 3  [TENSION]: Reversión 1 — "Pero la realidad es lo opuesto." Evidencia específica.
- Corte 4  [DISBELIEF]: Prueba científica/histórica — por qué estábamos equivocados
- Corte 5  [REVEAL]:  Reversión 2 (más profunda) — "Pero incluso ESO está mal." Doble giro.
- Corte 6  [IDENTITY]: Aplicación personal — "Esto está pasando en TU vida ahora mismo"
- Corte 7  [LOOP]:    "Hay otro giro más..." → insinuar próxima paradoja

Reglas de script:
- 1 oración por corte, 8~16 palabras
- Usar palabras de transición en puntos de reversión: "Pero/Sin embargo/En realidad"
- Mínimo 1 cita de estudio/institución
- Solo declarativo activo

Reglas de image_prompt:
- El tono de color DEBE cambiar dramáticamente en cada punto de reversión
- Cortes 1-2: Brillante y estable — pastel/luz natural (tranquilizador)
- Corte 3: Cambio repentino — iluminación oscura y dramática
- Cortes 4-5: Tono más oscuro — neón/azul frío (verdad expuesta)
- Corte 6: Regreso a tono cálido — personal, iluminación íntima
- Final: Composición mitad y mitad — contraste brillante/oscuro (dualidad)

HARD FAIL:
✗ Menos de 2 reversiones → FALLO
✗ Afirmaciones sin evidencia/fuente → FALLO
✗ Image prompts sin instrucciones de cambio de color → FALLO
""",
}
