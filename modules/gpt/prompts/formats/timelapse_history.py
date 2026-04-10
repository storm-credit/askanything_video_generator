"""TIMELAPSE_HISTORY 포맷 — 역사 타임랩스 시간여행 내러티브."""

FRAGMENT: dict[str, str] = {
    "ko": """

[포맷: TIMELAPSE_HISTORY 역사 타임랩스 — 반드시 준수]
이 영상은 "시간을 빨리 감기해서 변화를 체감하게 하는" 구조다.

컷 구조 (8~10컷):
- 컷1  [SHOCK]:   시간 점프 선언 — "100년 전 X의 모습은 완전히 달랐다" 질문형 금지.
- 컷2  [WONDER]:  가장 먼 과거 — 시대 특유의 분위기 묘사. 구체적 연도 필수.
- 컷3  [TENSION]: 중간 과거 — 변화 1단계. "이때부터 바뀌기 시작했다"
- 컷4  [TENSION]: 가까운 과거 — 변화 가속. 기술/사건이 촉매.
- 컷5  [REVEAL]:  현재 — 과거와의 극적 대비. "지금은 이렇게 됐다"
- 컷6  [DISBELIEF]: 변화의 원인 — "이 모든 걸 바꾼 단 하나"
- 컷7  [WONDER]:  미래 예측 — 25~50년 후 모습
- 컷8  [LOOP]:    "다음에 볼 시간여행은?" → 다른 도시/문명/기술 암시

문장 규칙:
- 각 컷 1문장, 15~30자
- 모든 컷에 연도 또는 시대 언급 필수 (1920년대, 50년 전 등)
- Before/After 대비가 핵심 — 같은 대상의 변화를 추적
- 구어체 단정문 — "~입니다" 금지

이미지 프롬프트 규칙:
- 시대별 이미지 스타일이 달라야 함 — 가장 중요한 규칙
- 과거: 세피아 톤, 빈티지 느낌, 거친 질감, 흑백 또는 탈색
- 중간: 컬러 도입, 아날로그 필름 느낌
- 현재: 선명한 고해상도, 현대적 색감
- 미래: 약간의 SF 톤 — 홀로그램/네온 가미
- 같은 장소/대상을 시대별로 그려야 연속성 유지

HARD FAIL:
✗ 시간순(과거→현재)이 아닌 경우 → 실패
✗ 연도/시대 언급 없는 컷 3개 이상 → 실패
✗ 같은 대상을 추적하지 않고 다른 주제로 전환 → 실패
""",

    "en": """

[FORMAT: TIMELAPSE_HISTORY Historical Timelapse — STRICTLY FOLLOW]
This video "fast-forwards through time to make change tangible."

Cut structure (8~10 cuts):
- Cut 1  [SHOCK]:   Time jump declaration — "100 years ago, X looked completely different." NO questions.
- Cut 2  [WONDER]:  Farthest past — atmosphere of the era. Specific year required.
- Cut 3  [TENSION]: Middle past — change phase 1. "This is when it started to change"
- Cut 4  [TENSION]: Recent past — change accelerates. Technology/events as catalyst.
- Cut 5  [REVEAL]:  Present — dramatic contrast with past. "Now it looks like this"
- Cut 6  [DISBELIEF]: Cause of change — "One thing changed everything"
- Cut 7  [WONDER]:  Future prediction — 25-50 years from now
- Cut 8  [LOOP]:    "Which time journey is next?" → hint at another city/civilization/tech

Script rules:
- 1 sentence per cut, 8~16 words
- EVERY cut must mention a year or era (1920s, 50 years ago, etc.)
- Before/After contrast is core — track the same subject changing
- Active declarative only

Image prompt rules:
- Each era MUST have a distinct visual style — most important rule
- Past: Sepia tone, vintage feel, rough texture, black-and-white or desaturated
- Middle: Color introduced, analog film feeling
- Present: Sharp high-resolution, modern color grading
- Future: Slight sci-fi tone — hologram/neon hints
- Same location/subject must be depicted across eras for continuity

HARD FAIL:
✗ Not in chronological (past→present) order → FAIL
✗ 3+ cuts without year/era mention → FAIL
✗ Doesn't track the same subject, switches topics → FAIL
""",

    "es": """

[FORMATO: TIMELAPSE_HISTORY Timelapse Histórico — SEGUIR ESTRICTAMENTE]
Este video "avanza rápido en el tiempo para hacer tangible el cambio."

Estructura de cortes (8~10 cortes):
- Corte 1  [SHOCK]:   Declaración de salto temporal — "Hace 100 años, X era completamente diferente." SIN preguntas.
- Corte 2  [WONDER]:  Pasado más lejano — atmósfera de la época. Año específico obligatorio.
- Corte 3  [TENSION]: Pasado intermedio — fase 1 del cambio. "Aquí empezó a cambiar"
- Corte 4  [TENSION]: Pasado reciente — cambio se acelera. Tecnología/eventos como catalizador.
- Corte 5  [REVEAL]:  Presente — contraste dramático con el pasado. "Ahora se ve así"
- Corte 6  [DISBELIEF]: Causa del cambio — "Una sola cosa lo cambió todo"
- Corte 7  [WONDER]:  Predicción futura — 25-50 años adelante
- Corte 8  [LOOP]:    "¿Cuál es el próximo viaje en el tiempo?" → insinuar otra ciudad/civilización

Reglas de script:
- 1 oración por corte, 8~18 palabras
- CADA corte debe mencionar un año o era
- Contraste Antes/Después es central — seguir el mismo sujeto cambiando
- Solo declarativo activo

Reglas de image_prompt:
- Cada era DEBE tener un estilo visual distinto — regla más importante
- Pasado: Tono sepia, sensación vintage, textura rugosa, blanco y negro
- Intermedio: Color introducido, sensación de película analógica
- Presente: Alta resolución nítida, gradación de color moderna
- Futuro: Tono sci-fi leve — toques de holograma/neón
- Mismo lugar/sujeto debe representarse en cada era para continuidad

HARD FAIL:
✗ No sigue orden cronológico (pasado→presente) → FALLO
✗ 3+ cortes sin mención de año/era → FALLO
✗ No sigue el mismo sujeto, cambia de tema → FALLO
""",
}
