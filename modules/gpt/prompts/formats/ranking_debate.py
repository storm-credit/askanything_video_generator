"""RANKING_DEBATE 포맷 — 논쟁 유발 랭킹 내러티브."""

FRAGMENT: dict[str, str] = {
    "ko": """

[포맷: RANKING_DEBATE 논쟁 랭킹 — 반드시 준수]
이 영상은 "동의/반박을 유발하는 순위 매기기" 구조다. 댓글 폭발이 목표.

컷 구조 (9~10컷):
- 컷1  [SHOCK]:   순위 선언 — "역대 최강 X 랭킹, 동의해?" 질문형 허용(유일한 예외).
- 컷2  [WONDER]:  채점 기준 공개 — 왜 이 순서인지 신뢰감 부여.
- 컷3  [TENSION]: 하위권 (6~5위) — 예상 가능한 선택으로 시작.
- 컷4  [TENSION]: 중위권 (4~3위) — 약간 의외. "이게 여기?"
- 컷5  [DISBELIEF]: 논쟁 포인트 — "이 순위에 동의 못하는 사람 많을 거다"
- 컷6  [URGENCY]: 2위 — 강력한 후보. "1위를 위협하는 존재"
- 컷7  [REVEAL]:  1위 발표 — 확고한 근거. Veo3 히어로컷.
- 컷8  [TENSION]: "하지만 이것도 있다" — 명예 언급/번외 후보
- 컷9  [IDENTITY]: "당신 생각은 다른가요?" — 강한 댓글 유도
- 컷10 [LOOP]:    "다음 랭킹은..." → 다른 카테고리 암시

문장 규칙:
- 각 컷 1문장, 15~30자
- 순위 번호 명시 필수
- 각 후보에 대한 근거 (수치/사례) 1개 이상
- 의견 유도 표현 허용 ("논란이지만", "반박 환영")
- 구어체 — "~입니다" 금지

이미지 프롬프트 규칙:
- 각 후보를 영웅적/권위적으로 표현 — 존중감 유지
- 컷1: 트로피/시상대 느낌 — 랭킹 분위기 설정
- 하위권: 보통 조명, 중립적 구도
- 상위권: 점점 더 극적 조명 — 골드/메달릭 색조
- 1위: 왕관/후광 느낌 — 최대 권위감
- 마지막: 물음표/빈 시상대 — 다음 편 암시

HARD FAIL:
✗ 순위 순서(하위→상위)가 아닌 경우 → 실패
✗ 채점 기준 제시 없이 순위만 나열 → 실패
✗ 1위에 근거 없이 발표 → 실패
""",

    "en": """

[FORMAT: RANKING_DEBATE Debate Ranking — STRICTLY FOLLOW]
This video is a "ranking that provokes agreement/disagreement." Comment explosion is the goal.

Cut structure (9~10 cuts):
- Cut 1  [SHOCK]:   Ranking declaration — "The all-time best X ranking — do you agree?" Question allowed (ONLY exception).
- Cut 2  [WONDER]:  Scoring criteria revealed — build trust with methodology.
- Cut 3  [TENSION]: Lower ranks (6th-5th) — predictable picks to start.
- Cut 4  [TENSION]: Mid ranks (4th-3rd) — slightly surprising. "This one HERE?"
- Cut 5  [DISBELIEF]: Debate point — "A lot of people will disagree with this ranking"
- Cut 6  [URGENCY]: 2nd place — strong contender. "The one threatening the throne"
- Cut 7  [REVEAL]:  1st place announcement — solid evidence. Veo3 hero cut.
- Cut 8  [TENSION]: "But there's also this" — honorable mention/wildcard
- Cut 9  [IDENTITY]: "Do YOU disagree?" — strong comment drive
- Cut 10 [LOOP]:    "Next ranking is..." → hint at different category

Script rules:
- 1 sentence per cut, 8~16 words
- Rank numbers MUST be stated
- Each candidate needs evidence (stats/examples) minimum 1
- Opinion-driving language allowed ("controversial but", "debate welcome")
- Active voice only

Image prompt rules:
- Each candidate portrayed heroically/authoritatively — maintain respect
- Cut 1: Trophy/podium feeling — set ranking atmosphere
- Lower ranks: Normal lighting, neutral composition
- Upper ranks: Progressively more dramatic — gold/metallic tones
- 1st place: Crown/halo feeling — maximum authority
- Final: Question mark/empty podium — hint next episode

HARD FAIL:
✗ Not in ascending order (low→high) → FAIL
✗ No scoring criteria, just listing → FAIL
✗ 1st place announced without evidence → FAIL
""",

    "es": """

[FORMATO: RANKING_DEBATE Ranking de Debate — SEGUIR ESTRICTAMENTE]
Este video es un "ranking que provoca acuerdo/desacuerdo." Explosión de comentarios es el objetivo.

Estructura de cortes (9~10 cortes):
- Corte 1  [SHOCK]:   Declaración de ranking — "El mejor X de todos los tiempos — ¿estás de acuerdo?" Pregunta permitida (ÚNICA excepción).
- Corte 2  [WONDER]:  Criterios de puntuación revelados — generar confianza con metodología.
- Corte 3  [TENSION]: Posiciones bajas (6°-5°) — elecciones predecibles para empezar.
- Corte 4  [TENSION]: Posiciones medias (4°-3°) — ligeramente sorprendente. "¿Este AQUÍ?"
- Corte 5  [DISBELIEF]: Punto de debate — "Mucha gente no estará de acuerdo con este ranking"
- Corte 6  [URGENCY]: 2° lugar — candidato fuerte. "El que amenaza el trono"
- Corte 7  [REVEAL]:  1° lugar anunciado — evidencia sólida. Corte héroe Veo3.
- Corte 8  [TENSION]: "Pero también está este" — mención honorable/comodín
- Corte 9  [IDENTITY]: "¿TÚ no estás de acuerdo?" — fuerte impulso de comentarios
- Corte 10 [LOOP]:    "El próximo ranking es..." → insinuar categoría diferente

Reglas de script:
- 1 oración por corte, 8~18 palabras
- Números de ranking DEBEN ser mencionados
- Cada candidato necesita evidencia (estadísticas/ejemplos) mínimo 1
- Lenguaje que impulse opinión permitido ("controversial pero", "debate bienvenido")
- Solo voz activa

Reglas de image_prompt:
- Cada candidato retratado heroica/autoritativamente — mantener respeto
- Corte 1: Sensación de trofeo/podio — establecer atmósfera de ranking
- Posiciones bajas: Iluminación normal, composición neutral
- Posiciones altas: Progresivamente más dramático — tonos dorado/metálico
- 1° lugar: Sensación de corona/halo — máxima autoridad
- Final: Signo de interrogación/podio vacío — insinuar próximo episodio

HARD FAIL:
✗ No está en orden ascendente (bajo→alto) → FALLO
✗ Sin criterios de puntuación, solo listado → FALLO
✗ 1° lugar anunciado sin evidencia → FALLO
""",
}
