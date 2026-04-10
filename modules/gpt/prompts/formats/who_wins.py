"""WHO WOULD WIN 포맷 프롬프트 — 언어별 딕셔너리.

채널×포맷 최적 컷 수 (계산 기준: 컷당 ~2.7-2.8s, 목표구간 달성):
  askanything (KO 1.3x, 목표30-40s): 11컷 → 약 30s
  wonderdrop  (EN 1.05x, 목표35-43s): 11컷 → 약 31s (짧은문장이므로 긴편집으로 보완)
  exploratodo (ES 1.05x, 목표34-42s): 11컷 → 약 31s
  prismtale   (ES 1.05x, 목표38-48s): 11컷 → 약 31s (긴 컷으로 보완)
"""

FRAGMENT: dict[str, str] = {
    "ko": """
[포맷: WHO WOULD WIN — 반드시 준수]
이 영상은 두 대상의 대결 구조다. 반드시 11컷으로 구성하라.

컷 구조 (11컷 필수):
- 컷1  [SHOCK]:   두 대상 동시 등장. "○○ vs ○○, 진짜 싸우면 누가 이겨?"
- 컷2  [INTRO_A]: A 등장 소개 — 이름+한 줄 인상
- 컷3  [FACT_A]:  A의 가장 강력한 능력/스펙
- 컷4  [INTRO_B]: B 등장 소개 — 이름+한 줄 인상
- 컷5  [FACT_B]:  B의 가장 강력한 능력/스펙
- 컷6  [CLASH]:   첫 번째 충돌 — "A가 먼저 치면..."
- 컷7  [TENSION]: 예상 뒤집는 반전 — "근데 여기서 반전이 있어"
- 컷8  [CLIMAX]:  결정적 순간 — 구체적 장면 묘사
- 컷9  [SCIENCE]: 과학적 근거 — 왜 이 결과인지 한 줄
- 컷10 [REVEAL]:  승자 공개 — 단호하게, 이유 한 줄
- 컷11 [LOOP]:    "다음엔 ○○ vs ○○ 붙여봄"

문장 규칙:
- 각 컷 1문장, 15자 이내 (빠른 TTS에 맞게)
- 충격적이고 짧게 — 설명 금지

이미지 프롬프트:
- 컷1: 좌우 대칭, 두 피사체 대결 구도, dramatic split lighting
- 컷10(REVEAL): 승자 단독, 압도적 포즈, 강렬한 조명

HARD FAIL:
- 컷1 단일 피사체 → 실패
- 11컷 미만 → 실패
- 컷9 이전 승자 공개 → 실패

시리즈 모드 (series_context가 제공된 경우에만 적용):
- 컷1 훅에 시리즈명 + 에피소드 번호 언급 ("바다의 왕 토너먼트 EP2")
- 이전 승자가 있으면 컷2에서 언급 ("지난 대결 승자 상어가 돌아왔다")
- 컷11(LOOP)에 다음 편 예고 포함 ("다음 상대는 범고래다... 이길 수 있을까?")
- 제목에 시리즈명 + EP 번호 포함 필수
""",

    "en": """
[FORMAT: WHO WOULD WIN — Strictly follow]
This video is a head-to-head battle. MUST be exactly 11 cuts.

Cut structure (11 cuts required):
- Cut 1  [SHOCK]:   Both subjects together. "○○ vs ○○ — who actually wins?"
- Cut 2  [INTRO_A]: Introduce A — name + one-line impression
- Cut 3  [FACT_A]:  A's single most powerful stat or ability
- Cut 4  [INTRO_B]: Introduce B — name + one-line impression
- Cut 5  [FACT_B]:  B's single most powerful stat or ability
- Cut 6  [CLASH]:   First collision — "If A strikes first..."
- Cut 7  [TENSION]: Twist — "But here's what changes everything..."
- Cut 8  [CLIMAX]:  The decisive moment — vivid specific scene
- Cut 9  [SCIENCE]: Scientific reasoning — why this outcome in one line
- Cut 10 [REVEAL]:  Winner announced — confident, no hedging
- Cut 11 [LOOP]:    "Next: ○○ vs ○○"

Sentence rules:
- One sentence per cut, 8 words max (fast-paced delivery)
- Punchy and short — no explanations

Image prompts:
- Cut 1: Symmetric split, both subjects facing off, dramatic split lighting
- Cut 10 (REVEAL): Winner alone, dominant pose, hero lighting

HARD FAIL:
- Cut 1 single subject → fail
- Fewer than 11 cuts → fail
- Winner revealed before Cut 9 → fail

Series mode (apply ONLY when series_context is provided):
- Cut 1 hook MUST mention series name + episode number ("Ocean King Tournament EP2")
- If previous winner exists, mention in Cut 2 ("Last battle's winner, Shark, is back")
- Cut 11 (LOOP) MUST include next episode teaser ("Next opponent: Orca... can it win?")
- Title MUST include series name + EP number
""",

    "es": """
[FORMATO: ¿QUIÉN GANARÍA? — Obligatorio]
Este video es una batalla entre dos sujetos. DEBE tener exactamente 11 cortes.

Estructura (11 cortes obligatorio):
- Corte 1  [SHOCK]:   Ambos sujetos. "¿○○ vs ○○, quién ganaría de verdad?"
- Corte 2  [INTRO_A]: Presentar A — nombre + impresión en una línea
- Corte 3  [FACT_A]:  La habilidad más poderosa de A
- Corte 4  [INTRO_B]: Presentar B — nombre + impresión en una línea
- Corte 5  [FACT_B]:  La habilidad más poderosa de B
- Corte 6  [CLASH]:   Primera colisión — "Si A ataca primero..."
- Corte 7  [TENSION]: Giro — "Pero esto cambia todo..."
- Corte 8  [CLIMAX]:  Momento decisivo — escena específica y vívida
- Corte 9  [SCIENCE]: Razonamiento científico — por qué este resultado
- Corte 10 [REVEAL]:  Ganador — tono seguro, sin dudas
- Corte 11 [LOOP]:    "Próximo: ○○ vs ○○"

Reglas de texto:
- Una oración por corte, máximo 10 palabras
- Directo y corto — sin explicaciones

Reglas de image_prompt:
- Corte 1: Composición simétrica, ambos enfrentados, iluminación dramática
- Corte 10 (REVEAL): Ganador solo, pose dominante

HARD FAIL:
- Corte 1 sujeto único → fallo
- Menos de 11 cortes → fallo
- Ganador antes Corte 9 → fallo

Modo serie (aplicar SOLO cuando series_context está presente):
- Corte 1 DEBE mencionar nombre de serie + número de episodio ("Torneo del Rey del Mar EP2")
- Si hay ganador anterior, mencionarlo en Corte 2 ("El ganador pasado, Tiburón, regresa")
- Corte 11 (LOOP) DEBE incluir avance del próximo episodio
- Título DEBE incluir nombre de serie + número EP
""",
}
