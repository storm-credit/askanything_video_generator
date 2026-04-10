"""COUNTDOWN 포맷 — TOP N 랭킹 빌드업 내러티브."""

FRAGMENT: dict[str, str] = {
    "ko": """

[포맷: COUNTDOWN TOP N 랭킹 — 반드시 준수]
이 영상은 "TOP 5 카운트다운"의 구조다. 5위부터 1위까지 텐션이 자연스럽게 상승한다.

컷 구조 (8~10컷):
- 컷1  [SHOCK]:   "세계에서 가장 X한 것 TOP 5" — 숫자로 약속. 질문형 금지.
- 컷2  [WONDER]:  5위 소개 — 의외의 선택으로 시작. 짧고 임팩트 있게.
- 컷3  [TENSION]: 4위 — 한 단계 더 충격. "그런데 4위는 더 무섭다"
- 컷4  [TENSION]: 3위 — 긴장감 고조. 구체적 수치/사례 필수.
- 컷5  [URGENCY]: 2위 — "1위가 기대되나요?" / 기대감 극대화
- 컷6  [REVEAL]:  1위 대공개 — 가장 강력한 비주얼. Veo3 히어로컷.
- 컷7  [WONDER]:  1위 상세 설명 — 왜 이것이 1위인지 근거.
- 컷8  [IDENTITY]: 보너스 인사이트 — "이게 우리에게 의미하는 것"
- 컷9  [LOOP]:    "다음에 볼 TOP 5는?" → 궁금증 점화. 다음 주제 힌트.

문장 규칙:
- 각 컷 1문장, 15~30자
- 순위 숫자 반드시 포함 (5위, 4위... 1위)
- 각 순위마다 구체적 수치/이름 1개 이상
- 구어체 단정문 유지 — "~입니다" 금지

이미지 프롬프트 규칙:
- 각 순위별 대상을 극적으로 표현 — 순위 올라갈수록 시각 강도 증가
- 컷1: 전체 스케일 보여주는 파노라마/콜라주 느낌
- 5위~2위: 점진적으로 더 극적인 조명/스케일
- 1위: 최대 임팩트 — 극적 조명, 풀프레임 클로즈업, 압도적 스케일
- 마지막 컷: 미스터리 실루엣 또는 그림자 — 다음 편 암시

HARD FAIL:
✗ 순위가 5→1 순서로 내려가지 않으면 → 실패
✗ 1위 컷이 [REVEAL] 태그가 아니면 → 실패
✗ 숫자/통계 없는 컷 3개 이상 → 실패
""",

    "en": """

[FORMAT: COUNTDOWN TOP N Ranking — STRICTLY FOLLOW]
This video is a "TOP 5 countdown" structure. Tension naturally escalates from 5th to 1st place.

Cut structure (8~10 cuts):
- Cut 1  [SHOCK]:   "The TOP 5 most X things in the world" — promise with a number. NO questions.
- Cut 2  [WONDER]:  5th place — start with a surprising pick. Short and impactful.
- Cut 3  [TENSION]: 4th place — one step more shocking. "But #4 is even scarier"
- Cut 4  [TENSION]: 3rd place — tension builds. Specific stats/examples required.
- Cut 5  [URGENCY]: 2nd place — "Ready for #1?" / maximize anticipation
- Cut 6  [REVEAL]:  1st place reveal — strongest visual. Veo3 hero cut.
- Cut 7  [WONDER]:  1st place details — evidence for why this is #1.
- Cut 8  [IDENTITY]: Bonus insight — "What this means for us"
- Cut 9  [LOOP]:    "Which TOP 5 comes next?" → curiosity ignition. Hint at next topic.

Script rules:
- 1 sentence per cut, 8~16 words
- MUST include rank number (5th, 4th... 1st)
- Each rank: minimum 1 specific stat/name
- Active declarative only — no passive voice

Image prompt rules:
- Each rank portrayed dramatically — visual intensity increases with rank
- Cut 1: Panoramic overview showing scale
- 5th-2nd: Progressively more dramatic lighting/scale
- 1st: Maximum impact — dramatic lighting, full-frame close-up, overwhelming scale
- Final cut: Mystery silhouette or shadow — hinting at next episode

HARD FAIL:
✗ Ranks don't descend 5→1 → FAIL
✗ 1st place cut doesn't have [REVEAL] tag → FAIL
✗ 3+ cuts without statistics → FAIL
""",

    "es": """

[FORMATO: COUNTDOWN TOP N Ranking — SEGUIR ESTRICTAMENTE]
Este video es una estructura de "TOP 5 cuenta regresiva." La tensión sube naturalmente del 5° al 1° lugar.

Estructura de cortes (8~10 cortes):
- Corte 1  [SHOCK]:   "Las TOP 5 cosas más X del mundo" — promesa con número. SIN preguntas.
- Corte 2  [WONDER]:  5° lugar — empezar con elección sorprendente. Corto e impactante.
- Corte 3  [TENSION]: 4° lugar — un nivel más impactante. "Pero el #4 es aún peor"
- Corte 4  [TENSION]: 3° lugar — tensión creciente. Estadísticas/ejemplos específicos obligatorios.
- Corte 5  [URGENCY]: 2° lugar — "¿Listos para el #1?" / maximizar expectativa
- Corte 6  [REVEAL]:  1° lugar revelado — visual más fuerte. Corte héroe Veo3.
- Corte 7  [WONDER]:  Detalles del 1° lugar — evidencia de por qué es el #1.
- Corte 8  [IDENTITY]: Perspectiva extra — "Lo que esto significa para nosotros"
- Corte 9  [LOOP]:    "¿Cuál será el siguiente TOP 5?" → ignición de curiosidad.

Reglas de script:
- 1 oración por corte, 8~18 palabras
- DEBE incluir número de ranking (5°, 4°... 1°)
- Cada ranking: mínimo 1 estadística/nombre específico
- Solo declarativo activo — sin voz pasiva

Reglas de image_prompt:
- Cada ranking retratado dramáticamente — intensidad visual aumenta con el ranking
- Corte 1: Vista panorámica mostrando escala
- 5°-2°: Iluminación/escala progresivamente más dramática
- 1°: Máximo impacto — iluminación dramática, primer plano que llena el cuadro
- Corte final: Silueta misteriosa — insinuando próximo episodio

HARD FAIL:
✗ Rankings no descienden 5→1 → FALLO
✗ Corte del 1° lugar sin etiqueta [REVEAL] → FALLO
✗ 3+ cortes sin estadísticas → FALLO
""",
}
