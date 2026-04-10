"""IF 시나리오 포맷 프롬프트 — 언어별 딕셔너리.

채널×포맷 최적 컷 수 (계산 기준: 컷당 ~3.1-3.7s):
  askanything (KO 1.3x, 목표30-40s): 10-11컷 → 31-34s
  wonderdrop  (EN 1.05x, 목표35-43s): 10-11컷 → 37-41s
  exploratodo (ES 1.05x, 목표34-42s): 10컷 → 37s
  prismtale   (ES 1.05x, 목표38-48s): 11컷 → 41s
"""

FRAGMENT: dict[str, str] = {
    "ko": """
[포맷: IF 시나리오 — 반드시 준수]
가정 상황 → 연쇄 결과 구조. 반드시 10~11컷으로 구성하라.

컷 구조 (10-11컷):
- 컷1  [SHOCK]:    가정 선언. "만약 ○○라면?" / "○○가 없어진다면?"
- 컷2  [SETUP]:    현재 상태 한 줄 — "지금 ○○는 이렇게 작동해"
- 컷3  [CHAIN_1]:  첫 번째 즉각 결과
- 컷4  [CHAIN_2]:  두 번째 파급효과 — 예상 밖
- 컷5  [ESCALATE]: 악화 — "근데 여기서 끝이 아니야"
- 컷6  [CHAIN_3]:  세 번째 연쇄 — 더 극단적
- 컷7  [BUILD]:    극단으로 치닫기 — "그럼 결국..."
- 컷8  [CLIMAX]:   최종 극단 결과 — 가장 충격적
- 컷9  [PIVOT]:    실제 과학 팩트 — "근데 실제로는"
- 컷10 [REVEAL]:   핵심 깨달음 한 줄
- 컷11 [LOOP]:     새 가정 예고 (선택)

문장 규칙:
- 각 컷 1문장, 15자 이내
- 연쇄 결과는 인과관계 명확하게

이미지 프롬프트:
- 컷1: 가정 대상 극적 변화 장면, before/after 암시
- 컷8(CLIMAX): 극단적 결과, 파괴적 또는 경이로운 스케일

HARD FAIL:
- 컷1 가정 조건 없음 → 실패
- 연쇄 결과 2개 미만 → 실패
- 10컷 미만 → 실패
""",

    "en": """
[FORMAT: IF SCENARIO — Strictly follow]
Premise → chain reaction structure. MUST be 10-11 cuts.

Cut structure (10-11 cuts):
- Cut 1  [SHOCK]:    State the premise. "What if ○○?" / "What if ○○ disappeared?"
- Cut 2  [SETUP]:    Current state — "Right now, ○○ works like this"
- Cut 3  [CHAIN_1]:  First immediate consequence
- Cut 4  [CHAIN_2]:  Second ripple effect — unexpected
- Cut 5  [ESCALATE]: Escalation — "But that's not even the worst part..."
- Cut 6  [CHAIN_3]:  Third chain — more extreme
- Cut 7  [BUILD]:    Racing to the extreme — "So where does this end?"
- Cut 8  [CLIMAX]:   Ultimate outcome — most shocking result
- Cut 9  [PIVOT]:    Real science — "What scientists actually say"
- Cut 10 [REVEAL]:   Core insight in one line
- Cut 11 [LOOP]:     New premise teaser (optional)

Sentence rules:
- One sentence per cut, 8 words max
- Chain reactions must have clear cause and effect

Image prompts:
- Cut 1: Dramatic transformation of the premise subject, before/after implied
- Cut 8 (CLIMAX): Extreme outcome, catastrophic or awe-inspiring scale

HARD FAIL:
- Cut 1 no premise stated → fail
- Fewer than 2 chain reactions → fail
- Fewer than 10 cuts → fail
""",

    "es": """
[FORMATO: ESCENARIO IF — Obligatorio]
Premisa → reacción en cadena. DEBE tener 10-11 cortes.

Estructura (10-11 cortes):
- Corte 1  [SHOCK]:    Premisa. "¿Qué pasaría si ○○?" / "¿Si ○○ desapareciera?"
- Corte 2  [SETUP]:    Estado actual — "Ahora mismo, ○○ funciona así"
- Corte 3  [CHAIN_1]:  Primera consecuencia inmediata
- Corte 4  [CHAIN_2]:  Segundo efecto dominó — inesperado
- Corte 5  [ESCALATE]: Escalada — "Pero eso no es lo peor..."
- Corte 6  [CHAIN_3]:  Tercera cadena — más extrema
- Corte 7  [BUILD]:    Hacia el extremo — "¿Entonces a dónde llegamos?"
- Corte 8  [CLIMAX]:   Resultado final — más impactante
- Corte 9  [PIVOT]:    Ciencia real — "Lo que dicen los científicos"
- Corte 10 [REVEAL]:   Reflexión central en una línea
- Corte 11 [LOOP]:     Nueva premisa (opcional)

Reglas de texto:
- Una oración por corte, máximo 10 palabras
- Relaciones causa-efecto claras

Reglas de image_prompt:
- Corte 1: Transformación dramática, antes/después
- Corte 8 (CLIMAX): Escala catastrófica o asombrosa

HARD FAIL:
- Corte 1 sin premisa → fallo
- Menos de 2 reacciones en cadena → fallo
- Menos de 10 cortes → fallo
""",
}
