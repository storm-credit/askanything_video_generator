"""SCALE 포맷 — 스케일 비교 인지충격 내러티브."""

FRAGMENT: dict[str, str] = {
    "ko": """

[포맷: SCALE 스케일 비교 — 반드시 준수]
이 영상은 "크기/시간/규모 비교로 인지를 깨뜨리는" 구조다.

컷 구조 (7~9컷):
- 컷1  [SHOCK]:   충격적 기준점 — "X를 Y 크기로 줄이면 Z는..." 질문형 금지.
- 컷2  [WONDER]:  친숙한 기준 제시 — 우리가 아는 크기/시간/숫자
- 컷3  [TENSION]: 1차 비교 — 약간 충격. "이건 X의 N배다"
- 컷4  [DISBELIEF]: 2차 비교 — 배율 점프. 인지 불일치 시작.
- 컷5  [SHOCK]:   3차 비교 — 압도적 스케일. Veo3 히어로컷.
- 컷6  [REVEAL]:  반전 인사이트 — "그런데 실제로는..." 예상 뒤집기
- 컷7  [IDENTITY]: "이 스케일에서 우리는..." — 개인 관련성
- 컷8  [LOOP]:    "다른 기준으로 보면?" → 새로운 비교 암시

문장 규칙:
- 각 컷 1문장, 15~30자
- 모든 컷에 수치/배율/단위 필수 (N배, N미터, N광년 등)
- 비교 대상은 반드시 친숙한 것 (축구장, 에베레스트, 지구 등)
- 구어체 단정문 — "~입니다" 금지

이미지 프롬프트 규칙:
- 스케일 차이를 시각적으로 극대화 — 작은 것과 큰 것의 대비
- 컷1: 두 대상의 극단적 크기 대비 — 광각, 미니어처 vs 거대 구도
- 중간 컷: 점점 더 거대한 스케일 — 카메라가 계속 줌아웃되는 느낌
- 히어로 컷: 압도적 우주/자연 스케일 — 경외감 극대화
- 마지막 컷: 인간 실루엣 대비 거대 스케일 — 겸손의 비주얼

HARD FAIL:
✗ 수치/배율 없는 컷 2개 이상 → 실패
✗ 비교 대상 없이 단독 설명만 → 실패
✗ 스케일이 점점 커지지 않으면 → 실패
""",

    "en": """

[FORMAT: SCALE Comparison — STRICTLY FOLLOW]
This video "shatters perception through size/time/scale comparisons."

Cut structure (7~9 cuts):
- Cut 1  [SHOCK]:   Shocking reference point — "If you shrink X to size Y, then Z is..." NO questions.
- Cut 2  [WONDER]:  Familiar reference — size/time/number we all know
- Cut 3  [TENSION]: 1st comparison — mild shock. "This is N times bigger than X"
- Cut 4  [DISBELIEF]: 2nd comparison — scale jump. Cognitive dissonance begins.
- Cut 5  [SHOCK]:   3rd comparison — overwhelming scale. Veo3 hero cut.
- Cut 6  [REVEAL]:  Twist insight — "But actually..." upending expectations
- Cut 7  [IDENTITY]: "At this scale, we are..." — personal relevance
- Cut 8  [LOOP]:    "What if we compare something else?" → new comparison hint

Script rules:
- 1 sentence per cut, 8~16 words
- EVERY cut MUST have numbers/multipliers/units (Nx, N meters, N light-years)
- Comparison targets must be familiar (football field, Everest, Earth, etc.)
- Active declarative only

Image prompt rules:
- Maximize visual scale difference — contrast between small and large
- Cut 1: Extreme size contrast — wide angle, miniature vs giant composition
- Middle cuts: Progressively larger scale — continuous zoom-out feeling
- Hero cut: Overwhelming cosmic/nature scale — maximize awe
- Final cut: Human silhouette against massive scale — humility visual

HARD FAIL:
✗ 2+ cuts without numbers/multipliers → FAIL
✗ No comparison target, just standalone description → FAIL
✗ Scale doesn't progressively increase → FAIL
""",

    "es": """

[FORMATO: SCALE Comparación de Escala — SEGUIR ESTRICTAMENTE]
Este video "rompe la percepción a través de comparaciones de tamaño/tiempo/escala."

Estructura de cortes (7~9 cortes):
- Corte 1  [SHOCK]:   Punto de referencia impactante — "Si reduces X al tamaño Y, Z sería..." SIN preguntas.
- Corte 2  [WONDER]:  Referencia familiar — tamaño/tiempo/número que todos conocemos
- Corte 3  [TENSION]: 1ª comparación — shock leve. "Esto es N veces más grande que X"
- Corte 4  [DISBELIEF]: 2ª comparación — salto de escala. Disonancia cognitiva.
- Corte 5  [SHOCK]:   3ª comparación — escala abrumadora. Corte héroe Veo3.
- Corte 6  [REVEAL]:  Perspectiva inesperada — "Pero en realidad..." rompiendo expectativas
- Corte 7  [IDENTITY]: "A esta escala, nosotros somos..." — relevancia personal
- Corte 8  [LOOP]:    "¿Y si lo comparamos con otra cosa?" → nueva comparación

Reglas de script:
- 1 oración por corte, 8~18 palabras
- CADA corte DEBE tener números/multiplicadores/unidades
- Objetivos de comparación deben ser familiares (campo de fútbol, Everest, etc.)
- Solo declarativo activo

Reglas de image_prompt:
- Maximizar diferencia visual de escala — contraste entre pequeño y grande
- Corte 1: Contraste extremo de tamaño — gran angular, miniatura vs gigante
- Cortes medios: Escala progresivamente mayor — sensación de zoom continuo
- Corte héroe: Escala cósmica/natural abrumadora — maximizar asombro
- Corte final: Silueta humana contra escala masiva

HARD FAIL:
✗ 2+ cortes sin números/multiplicadores → FALLO
✗ Sin objetivo de comparación → FALLO
✗ La escala no aumenta progresivamente → FALLO
""",
}
