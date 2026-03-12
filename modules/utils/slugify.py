import re


def _safe_slug(text: str, *, max_len: int) -> str:
    cleaned = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return (cleaned or "topic")[:max_len]


def slugify_topic(topic: str, lang: str = "ko") -> str:
    topic = (topic or "").strip()

    if lang == "ko":
        try:
            from konlpy.tag import Okt

            okt = Okt()
            nouns = okt.nouns(topic)
            keywords = "_".join(nouns[:2]) if nouns else topic
        except Exception:
            keywords = topic

        return _safe_slug(keywords, max_len=60)

    return _safe_slug(topic.lower(), max_len=30)
