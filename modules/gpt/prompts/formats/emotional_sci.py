"""감성과학 포맷 프롬프트 — 언어별 딕셔너리.

채널×포맷 최적 컷 수 (계산 기준: 컷당 ~3.9-4.7s, 긴 감성 문장):
  askanything (KO 1.3x, 목표30-40s): 8-9컷 → 31-39s ✅
  wonderdrop  (EN 1.05x, 목표35-43s): 8컷 → 38s ✅
  exploratodo (ES 1.05x, 목표34-42s): 8컷 → 38s ✅
  prismtale   (ES 1.05x, 목표38-48s): 9-10컷 → 42-47s ✅
"""

FRAGMENT: dict[str, str] = {
    "ko": """
[포맷: 감성과학 — 반드시 준수]
과학 팩트를 감성으로 풀어내는 구조. 8~9컷. 충격보다 공감이 핵심.

컷 구조 (8-9컷) + 감정 태그 (description 필드에 반드시 포함):
- 컷1 [WONDER]:   일상 질문/상황으로 시작. "혹시 ○○한 적 있어?"
- 컷2 [TENSION]:  과학 팩트 — 이야기하듯, 교과서체 금지
- 컷3 [IDENTITY]: 인간 경험 연결 — "즉, 지금 우리 몸이 ○○하고 있어"
- 컷4 [WONDER]:   경이로움 증폭 — 숫자/규모로 뒷받침
- 컷5 [TENSION]:  실감나게 — "그게 얼마나 큰 거냐면..."
- 컷6 [IDENTITY]: 감정 전환점 — 따뜻하거나 경이롭거나
- 컷7 [REVEAL]:   핵심 깨달음 — "○○이 이런 의미였어"
- 컷8 [WONDER]:   여운 — "그리고 지금 이 순간에도..."
- 컷9 [IDENTITY]: 추가 팩트 (선택 — prismtale 9컷 시)

감정 태그 규칙:
- SHOCK 절대 사용 금지 (충격형 포맷과 혼용 금지)
- WONDER(경이) / IDENTITY(공감) / REVEAL(깨달음) / TENSION(궁금증) 만 사용
- 컷1 반드시 [WONDER] 태그 (첫 컷 영상 생성 보장)

톤 규칙:
- 반말, 친구한테 이야기하듯
- 충격형 훅 절대 금지
- 의료 조언 표현 금지 ("○○하면 건강해진다" 등)
- 문장 길이: 15-20자 (감성적으로 천천히)

이미지 프롬프트:
- 따뜻한 색감, 인간적 스케일
- 현미경 단면, 체내 시점, 자연 — 아름답고 경이롭게
- 폭력적/충격적 이미지 금지

HARD FAIL:
- 충격형 훅 시작 → 포맷 위반
- 의료 조언 포함 → 정책 위반
- 8컷 미만 → 실패
""",

    "en": """
[FORMAT: EMOTIONAL SCIENCE — Strictly follow]
Science through emotional resonance. 8 cuts. Empathy over shock.

Cut structure (8 cuts) + emotion tags (must appear in description field):
- Cut 1 [WONDER]:   Relatable everyday moment. "Have you ever ○○?"
- Cut 2 [TENSION]:  The science — conversational, never textbook
- Cut 3 [IDENTITY]: Human connection — "In other words, your body is ○○ right now"
- Cut 4 [WONDER]:   Amplify wonder — with scale or number
- Cut 5 [TENSION]:  Make it tangible — "To put that in perspective..."
- Cut 6 [IDENTITY]: Emotional turning point — warm, poignant, or awe-inspiring
- Cut 7 [REVEAL]:   Core insight — "This is what ○○ actually means"
- Cut 8 [WONDER]:   Lingering thought — "And even right now, as you watch this..."

Emotion tag rules:
- NEVER use [SHOCK] — absolute prohibition in this format
- Only use: [WONDER] [IDENTITY] [REVEAL] [TENSION]
- Cut 1 MUST be [WONDER] — ensures first cut gets video generation

Tone rules:
- Conversational, warm — like talking to a friend
- NO shock hooks — absolute prohibition
- No medical advice language
- Sentence length: 8-12 words (slow, emotional delivery)

Image prompts:
- Warm tones, human scale
- Microscopic sections, body interior, nature — beautiful and wondrous
- No violent or disturbing imagery

HARD FAIL:
- Shock hook at start → format violation
- Medical advice language → policy violation
- Fewer than 8 cuts → fail
""",

    "es": """
[FORMATO: CIENCIA EMOCIONAL — Obligatorio]
Ciencia a través de la emoción. 8-9 cortes. Empatía sobre impacto.

Estructura (8-9 cortes) + etiquetas emocionales (deben aparecer en el campo description):
- Corte 1 [WONDER]:   Momento cotidiano. "¿Alguna vez ○○?"
- Corte 2 [TENSION]:  Ciencia — conversacional, nunca libro de texto
- Corte 3 [IDENTITY]: Conexión humana — "Es decir, tu cuerpo está ○○ ahora mismo"
- Corte 4 [WONDER]:   Ampliar asombro — con cifra o escala
- Corte 5 [TENSION]:  Hacerlo tangible — "Para dimensionarlo..."
- Corte 6 [IDENTITY]: Punto emocional — cálido, conmovedor o inspirador
- Corte 7 [REVEAL]:   Reflexión central — "Esto es lo que realmente significa ○○"
- Corte 8 [WONDER]:   Pensamiento que perdura — "Y en este mismo momento..."
- Corte 9 [IDENTITY]: Dato adicional (opcional — prismtale)

Reglas de etiquetas emocionales:
- NUNCA usar [SHOCK] — prohibición absoluta en este formato
- Solo usar: [WONDER] [IDENTITY] [REVEAL] [TENSION]
- Corte 1 DEBE ser [WONDER] — garantiza generación de video en el primer corte

Reglas de tono:
- Conversacional, cálido
- Sin hooks de impacto — prohibición absoluta
- Sin lenguaje de consejo médico
- Longitud de frase: 10-15 palabras (ritmo lento y emotivo)

Reglas de image_prompt:
- Tonos cálidos, escala humana
- Secciones microscópicas, interior del cuerpo — hermoso y asombroso
- Sin imágenes violentas

HARD FAIL:
- Hook de impacto al inicio → violación de formato
- Lenguaje de consejo médico → violación de política
- Menos de 8 cortes → fallo
""",
}
