import re

# Okt() 인스턴스 캐시 (JVM 초기화 비용 ~2-3초 → 최초 1회만)
_okt_instance = None


def _get_okt():
    global _okt_instance
    if _okt_instance is None:
        from konlpy.tag import Okt
        _okt_instance = Okt()
    return _okt_instance


def _safe_slug(text: str, *, max_len: int) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return (cleaned or "topic")[:max_len]


def slugify_topic(topic: str, lang: str = "ko") -> str:
    topic = (topic or "").strip()

    if lang == "ko":
        try:
            okt = _get_okt()
            nouns = okt.nouns(topic)
            keywords = "_".join(nouns[:2]) if nouns else topic
        except Exception as e:
            print(f"[Slugify] 형태소 분석 실패, 원문 사용: {e}")
            keywords = topic

        return _safe_slug(keywords, max_len=60)

    return _safe_slug(topic.lower(), max_len=30)
