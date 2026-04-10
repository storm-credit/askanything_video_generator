"""FUTURE_VISION 포맷 — 미래 예측 FOMO 내러티브."""

FRAGMENT: dict[str, str] = {
    "ko": """

[포맷: FUTURE_VISION 미래 예측 — 반드시 준수]
이 영상은 "미래를 보여주고 FOMO를 자극하는" 구조다.

컷 구조 (8~10컷):
- 컷1  [SHOCK]:   충격적 미래 선언 — "2050년, X는 사라진다" 질문형 금지.
- 컷2  [WONDER]:  현재 상태 — 기준점 제시. 지금 우리가 아는 세계.
- 컷3  [TENSION]: 변화 신호 #1 — "이미 시작됐다." 현재 진행중인 변화.
- 컷4  [TENSION]: 변화 신호 #2 — 가속화되는 변화. 수치 증가율 포함.
- 컷5  [URGENCY]: 2030년 예측 — 가까운 미래. 체감 가능한 변화.
- 컷6  [SHOCK]:   2050년 예측 — 극적 미래 비주얼. Veo3 히어로컷.
- 컷7  [REVEAL]:  생존 전략 — "이 변화에서 살아남으려면..."
- 컷8  [DISBELIEF]: 반전 — "하지만 전문가들은 틀렸을 수도 있다"
- 컷9  [LOOP]:    "다음에 알아볼 미래는?" → 궁금증 유도

문장 규칙:
- 각 컷 1문장, 15~30자
- 연도/시기 언급 필수 (2030, 2050, 10년 후 등)
- 전문가/기관 인용 최소 1회
- 구어체 단정문 — "~입니다" 금지

이미지 프롬프트 규칙:
- 시간 흐름: 현재→미래로 비주얼 스타일이 점진적으로 변화
- 컷1~2: 현재 — 자연스러운 조명, 현실적 색감
- 컷3~4: 근미래 — 약간 SF 톤, 블루/실버 색조 가미
- 컷5~6: 먼 미래 — 완전 SF, 네온/홀로그램/우주적 스케일
- 컷7: 인간 실루엣 vs 미래 풍경 — 생존 테마
- 마지막: 미스터리 — 물음표 느낌, 어두운 실루엣

HARD FAIL:
✗ 미래 연도/시기 언급 없는 컷 4개 이상 → 실패
✗ 현재→미래 시간순이 아닌 경우 → 실패
✗ "~일 수도 있다" 같은 모호한 표현이 3회 이상 → 실패
""",

    "en": """

[FORMAT: FUTURE_VISION Future Prediction — STRICTLY FOLLOW]
This video "shows the future and triggers FOMO."

Cut structure (8~10 cuts):
- Cut 1  [SHOCK]:   Shocking future declaration — "By 2050, X will be gone." NO questions.
- Cut 2  [WONDER]:  Current state — baseline. The world as we know it now.
- Cut 3  [TENSION]: Change signal #1 — "It's already happening." Currently unfolding changes.
- Cut 4  [TENSION]: Change signal #2 — accelerating change. Include growth rates.
- Cut 5  [URGENCY]: 2030 prediction — near future. Tangible changes.
- Cut 6  [SHOCK]:   2050 prediction — dramatic future visual. Veo3 hero cut.
- Cut 7  [REVEAL]:  Survival strategy — "To survive this change..."
- Cut 8  [DISBELIEF]: Plot twist — "But experts might be wrong"
- Cut 9  [LOOP]:    "What future topic comes next?" → curiosity trigger

Script rules:
- 1 sentence per cut, 8~16 words
- Year/timeframe mentions required (2030, 2050, in 10 years, etc.)
- Minimum 1 expert/institution citation
- Active declarative only — no passive voice

Image prompt rules:
- Time progression: visual style gradually shifts from present to future
- Cuts 1-2: Present — natural lighting, realistic colors
- Cuts 3-4: Near future — slight sci-fi tone, blue/silver tints
- Cuts 5-6: Far future — full sci-fi, neon/hologram/cosmic scale
- Cut 7: Human silhouette vs future landscape — survival theme
- Final: Mystery — question mark feeling, dark silhouette

HARD FAIL:
✗ 4+ cuts without future year/timeframe → FAIL
✗ Not in chronological present→future order → FAIL
✗ 3+ vague "might/could be" expressions → FAIL
""",

    "es": """

[FORMATO: FUTURE_VISION Predicción del Futuro — SEGUIR ESTRICTAMENTE]
Este video "muestra el futuro y provoca FOMO."

Estructura de cortes (8~10 cortes):
- Corte 1  [SHOCK]:   Declaración futura impactante — "Para 2050, X desaparecerá." SIN preguntas.
- Corte 2  [WONDER]:  Estado actual — línea base. El mundo como lo conocemos.
- Corte 3  [TENSION]: Señal de cambio #1 — "Ya está pasando." Cambios en curso.
- Corte 4  [TENSION]: Señal de cambio #2 — cambio acelerado. Incluir tasas de crecimiento.
- Corte 5  [URGENCY]: Predicción 2030 — futuro cercano. Cambios tangibles.
- Corte 6  [SHOCK]:   Predicción 2050 — visual dramático del futuro. Corte héroe Veo3.
- Corte 7  [REVEAL]:  Estrategia de supervivencia — "Para sobrevivir a este cambio..."
- Corte 8  [DISBELIEF]: Giro — "Pero los expertos podrían estar equivocados"
- Corte 9  [LOOP]:    "¿Qué futuro exploramos después?" → activador de curiosidad

Reglas de script:
- 1 oración por corte, 8~18 palabras
- Menciones de año/plazo obligatorias (2030, 2050, en 10 años, etc.)
- Mínimo 1 cita de experto/institución
- Solo declarativo activo — sin voz pasiva

Reglas de image_prompt:
- Progresión temporal: estilo visual cambia gradualmente de presente a futuro
- Cortes 1-2: Presente — iluminación natural, colores realistas
- Cortes 3-4: Futuro cercano — tono sci-fi leve, tintes azul/plata
- Cortes 5-6: Futuro lejano — sci-fi completo, neón/holograma/escala cósmica
- Corte 7: Silueta humana vs paisaje futuro — tema de supervivencia
- Final: Misterio — sensación de signo de interrogación, silueta oscura

HARD FAIL:
✗ 4+ cortes sin año/plazo futuro → FALLO
✗ No sigue orden cronológico presente→futuro → FALLO
✗ 3+ expresiones vagas "podría/tal vez" → FALLO
""",
}
