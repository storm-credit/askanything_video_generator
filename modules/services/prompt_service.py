"""채널별 프롬프트/주제 변형 생성 서비스.

사용:
    from modules.services.prompt_service import prompt_service
    jobs = prompt_service.build_prompt_jobs("topic_001", "토성은 물에 뜰 수 있다", "askanything")
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List


@dataclass
class PromptJob:
    job_id: str
    channel: str
    topic_id: str
    topic: str
    prompt: str
    aspect_ratio: str = "9:16"
    style: str = "default"
    language: str = "en"


class PromptService:
    def build_prompt_jobs(self, topic_id: str, topic: str, channel: str, count: int = 4) -> List[PromptJob]:
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
        return builder(topic_id, topic, count)

    def _build_askanything(self, tid: str, topic: str, count: int) -> List[PromptJob]:
        styles = [
            "dramatic cinematic lighting, highly clickable, curiosity-driven visual",
            "bold contrast, mysterious atmosphere, strong focal point",
            "clean composition, short-form science thumbnail style, emotionally striking",
            "viral shorts style, simple but shocking visual metaphor",
        ]
        return [PromptJob(
            job_id=f"{tid}-askanything-{i+1}", channel="askanything", topic_id=tid, topic=topic,
            prompt=f"{topic}, {s}, vertical composition, high visual clarity, no watermark, no text",
            style=f"askanything_{i+1}", language="ko",
        ) for i, s in enumerate(styles[:count])]

    def _build_wonderdrop(self, tid: str, topic: str, count: int) -> List[PromptJob]:
        styles = [
            "clean educational visual, modern science explainer style",
            "simple but awe-inspiring composition, premium documentary feel",
            "clear central subject, polished and trustworthy visual tone",
            "minimal cinematic science poster look, elegant lighting",
        ]
        return [PromptJob(
            job_id=f"{tid}-wonderdrop-{i+1}", channel="wonderdrop", topic_id=tid, topic=topic,
            prompt=f"{topic}, {s}, vertical frame, high detail, no text, no watermark",
            style=f"wonderdrop_{i+1}", language="en",
        ) for i, s in enumerate(styles[:count])]

    def _build_exploratodo(self, tid: str, topic: str, count: int) -> List[PromptJob]:
        styles = [
            "emotional and vivid visual, strong sense of wonder",
            "dramatic but accessible educational image, visually exciting",
            "high-impact thumbnail style for Spanish-speaking audience",
            "bright contrast, curiosity, emotional storytelling visual",
        ]
        return [PromptJob(
            job_id=f"{tid}-exploratodo-{i+1}", channel="exploratodo", topic_id=tid, topic=topic,
            prompt=f"{topic}, {s}, vertical layout, bold visual storytelling, no text, no watermark",
            style=f"exploratodo_{i+1}", language="es",
        ) for i, s in enumerate(styles[:count])]

    def _build_prismtale(self, tid: str, topic: str, count: int) -> List[PromptJob]:
        styles = [
            "moody cinematic realism, mysterious atmosphere, dark elegant composition",
            "low-key lighting, shadowy depth, refined science mystery visual",
            "atmospheric dark documentary style, subtle glow, ominous tone",
            "elegant noir science visual, minimal but haunting composition",
        ]
        return [PromptJob(
            job_id=f"{tid}-prismtale-{i+1}", channel="prismtale", topic_id=tid, topic=topic,
            prompt=f"{topic}, {s}, vertical frame, no text, no watermark",
            style=f"prismtale_{i+1}", language="es",
        ) for i, s in enumerate(styles[:count])]


prompt_service = PromptService()
