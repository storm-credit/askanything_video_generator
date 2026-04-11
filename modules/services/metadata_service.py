"""채널별 제목/설명/태그 생성 서비스.

사용:
    from modules.services.metadata_service import metadata_service
    meta = metadata_service.build_metadata("wonderdrop", topic_data)
"""
from __future__ import annotations
from typing import Dict


class MetadataService:
    def build_metadata(self, channel: str, topic_data: Dict) -> Dict:
        channel = channel.lower()
        builders = {
            "askanything": self._build_askanything,
            "wonderdrop": self._build_wonderdrop,
            "exploratodo": self._build_exploratodo,
            "prismtale": self._build_prismtale,
        }
        builder = builders.get(channel)
        if not builder:
            raise ValueError(f"Unknown channel: {channel}")
        return builder(topic_data)

    def _build_askanything(self, d: Dict) -> Dict:
        title = d.get("title_ko", d.get("title", d.get("topic", "")))
        desc = d.get("desc_ko", d.get("description", f"{title}\n#과학 #신기한사실"))
        tags = d.get("tags_ko", d.get("tags", ["과학", "신기한사실"]))
        if isinstance(tags, str):
            tags = [t.strip().lstrip("#") for t in tags.split() if t.strip()]
        return {"title": self._trim(title, 60), "description": desc, "tags": tags, "language": "ko", "category_id": "27"}

    def _build_wonderdrop(self, d: Dict) -> Dict:
        title = d.get("title_en", d.get("title", d.get("topic", "")))
        desc = d.get("desc_en", d.get("description", f"{title}\n#science #facts"))
        tags = d.get("tags_en", d.get("tags", ["science", "facts"]))
        if isinstance(tags, str):
            tags = [t.strip().lstrip("#") for t in tags.split() if t.strip()]
        return {"title": self._trim(title, 70), "description": desc, "tags": tags, "language": "en", "category_id": "27"}

    def _build_exploratodo(self, d: Dict) -> Dict:
        title = d.get("title_es", d.get("title", d.get("topic", "")))
        desc = d.get("desc_es", d.get("description", f"{title}\n#ciencia #datos"))
        tags = d.get("tags_es", d.get("tags", ["ciencia", "datos"]))
        if isinstance(tags, str):
            tags = [t.strip().lstrip("#") for t in tags.split() if t.strip()]
        return {"title": self._trim(title, 70), "description": desc, "tags": tags, "language": "es", "category_id": "27"}

    def _build_prismtale(self, d: Dict) -> Dict:
        title = d.get("title_es_us", d.get("title_es", d.get("title", d.get("topic", ""))))
        desc = d.get("desc_es_us", d.get("desc_es", d.get("description", f"{title}\n#ciencia #misterio")))
        tags = d.get("tags_es_us", d.get("tags_es", d.get("tags", ["ciencia", "misterio"])))
        if isinstance(tags, str):
            tags = [t.strip().lstrip("#") for t in tags.split() if t.strip()]
        return {"title": self._trim(title, 70), "description": desc, "tags": tags, "language": "es", "category_id": "27"}

    @staticmethod
    def _trim(title: str, max_len: int) -> str:
        title = title.strip()
        return title if len(title) <= max_len else title[:max_len-1].rstrip() + "..."


metadata_service = MetadataService()
