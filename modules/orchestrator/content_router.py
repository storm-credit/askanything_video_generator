"""콘텐츠 유형 자동 라우팅 — 토픽 분석 → 비주얼 방식 결정.

ScriptAgent 실행 후, 토픽+컷 내용을 분석하여 최적 비주얼 방식 결정:
  - "blender_3d": Blender 3D (크기 비교, 궤도, 단면도)
  - "veo3": AI 영상 (시네마틱, 동적 장면)
  - "imagen": 정지 이미지 + Ken Burns (기본, 대부분의 콘텐츠)
"""

from __future__ import annotations

import re

# ── 콘텐츠 유형별 키워드 매핑 ──

# Blender 3D가 더 나은 주제들
BLENDER_KEYWORDS = {
    # 크기/스케일 비교
    "크기 비교", "size comparison", "comparación de tamaño",
    "얼마나 큰", "how big", "how large", "how tall",
    "스케일", "scale",
    # 행성/천체 구조
    "태양계", "solar system", "sistema solar",
    "궤도", "orbit", "órbita",
    "행성 크기", "planet size", "tamaño del planeta",
    "별 크기", "star size", "uy scuti", "UY Scuti",
    # 단면/내부 구조
    "단면", "cross section", "sección transversal",
    "내부 구조", "internal structure", "estructura interna",
    "지구 내부", "earth interior", "inside earth",
    # 높이/깊이 비교
    "깊이 비교", "depth comparison",
    "높이 비교", "height comparison",
    "마리아나 해구", "mariana trench",
}

# Veo3 AI 영상이 더 나은 주제들
VEO3_KEYWORDS = {
    # 동적 자연 현상 (블랙홀 관련 여러 표현)
    "블랙홀", "black hole", "agujero negro", "blackhole",
    "빠지면", "fell into", "sucked into",  # 블랙홀 맥락 강화
    "초신성", "supernova",
    "성운", "nebula", "nebulosa",
    "폭발", "explosion", "explosión",
    "충돌", "collision", "colisión", "impact",
    # 동물 행동
    "사냥", "hunting", "caza",
    "포식자", "predator", "depredador",
    "이동", "migration", "migración",
    # 자연 현상
    "화산", "volcano", "volcán",
    "쓰나미", "tsunami",
    "번개", "lightning", "rayo",
    "토네이도", "tornado",
    # 시네마틱 장면
    "우주 비행", "space flight",
    "심해 탐사", "deep sea exploration",
}


def classify_content(topic: str, cuts: list[dict] | None = None) -> str:
    """토픽과 컷 내용을 분석하여 최적 비주얼 방식 결정.

    Args:
        topic: 원본 토픽 문자열
        cuts: 생성된 컷 리스트 (있으면 더 정확한 분류)

    Returns:
        "blender_3d", "veo3", "imagen" 중 하나
    """
    topic_lower = topic.lower()

    # 컷 내용도 분석 대상에 포함
    all_text = topic_lower
    if cuts:
        for cut in cuts:
            all_text += " " + cut.get("script", "").lower()
            all_text += " " + cut.get("description", "").lower()
            all_text += " " + cut.get("prompt", "").lower()

    # 1. Blender 키워드 매칭
    blender_score = sum(1 for kw in BLENDER_KEYWORDS if kw.lower() in all_text)

    # 2. Veo3 키워드 매칭
    veo3_score = sum(1 for kw in VEO3_KEYWORDS if kw.lower() in all_text)

    # 3. 크기 비교 패턴 탐지 (정규식)
    size_patterns = [
        r"\d+배",           # "100배"
        r"\d+\s*times",     # "100 times"
        r"\d+\s*veces",     # "100 veces"
        r"vs\.?\s",         # "Earth vs Sun"
        r"보다\s*(크|작|높|깊|넓)",  # "~보다 큰"
        r"bigger|smaller|larger|taller|deeper",
        r"más grande|más pequeño",
    ]
    size_match_count = sum(1 for p in size_patterns if re.search(p, all_text))
    blender_score += size_match_count * 2  # 크기 비교 패턴은 가중치 2배

    # 판단
    if blender_score >= 3:
        return "blender_3d"
    elif veo3_score >= 2:
        return "veo3"
    else:
        return "imagen"


def get_visual_recommendation(content_type: str) -> dict:
    """콘텐츠 유형에 따른 비주얼 설정 추천.

    Returns:
        {"visual_type": str, "video_engine": str, "description": str}
    """
    recommendations = {
        "blender_3d": {
            "visual_type": "blender_3d",
            "video_engine": "none",  # Blender가 직접 영상 생성
            "image_engine": "imagen",  # 비교용 배경 이미지는 Imagen
            "description": "3D 크기 비교/구조 시각화 (Blender)",
        },
        "veo3": {
            "visual_type": "veo3",
            "video_engine": "veo3",
            "image_engine": "imagen",
            "description": "시네마틱 AI 영상 변환 (Veo3)",
        },
        "imagen": {
            "visual_type": "imagen",
            "video_engine": "none",
            "image_engine": "imagen",
            "description": "정지 이미지 + Ken Burns (기본)",
        },
    }
    return recommendations.get(content_type, recommendations["imagen"])
