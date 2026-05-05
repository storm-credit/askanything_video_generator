import asyncio

from modules.gpt.cutter.generator import _build_series_context_instruction, _extract_series_title
from modules.orchestrator.agents.script import ScriptAgent
from modules.orchestrator.base import AgentContext, ModelRouter
from modules.orchestrator.tracker import TokenTracker
from modules.scheduler.topic_generator import _build_format_slate_rules


def test_weekly_topic_rules_make_who_wins_a_series_lane():
    rules = _build_format_slate_rules(7)

    assert "WHO_WINS 2-3개" in rules
    assert "askanything 전용 연속 VS 시리즈 레인" in rules
    assert "[시리즈:...]" in rules
    assert "단발/고립 VS는 탈락" in rules
    assert "WHO_WINS 최대 1-2개" not in rules


def test_short_range_topic_rules_require_vs_series_continuity():
    rules = _build_format_slate_rules(3)

    assert "WHO_WINS는 askanything 전용 연속 VS 시리즈로 최소 1개" in rules
    assert "다음 상대 예고" in rules
    assert "단발 VS는 탈락" in rules


def test_who_wins_series_instruction_is_injected_only_for_series():
    instruction = _build_series_context_instruction(
        "WHO_WINS",
        "ko",
        series_title="우주대전",
        series_context="previous_winner: 태양\nnext_challenger: 블랙홀",
    )

    assert "<series_context>" in instruction
    assert "series_title: 우주대전" in instruction
    assert "previous_winner: 태양" in instruction
    assert "컷11은 다음 도전자 또는 다음 편을 반드시 예고" in instruction
    assert _build_series_context_instruction("FACT", "ko", series_title="우주대전") == ""


def test_series_title_can_be_inferred_from_topic_tag():
    assert _extract_series_title("태양 vs 블랙홀 [포맷:WHO_WINS] [시리즈:우주대전]") == "우주대전"


def test_script_agent_passes_series_context_to_generator(monkeypatch):
    import modules.gpt.cutter as cutter_module

    captured = {}

    def fake_generate_cuts(*args, **kwargs):
        captured.update(kwargs)
        return (
            [
                {
                    "script": "태양 vs 블랙홀, 누가 이길까?",
                    "prompt": "Sun and black hole face off, cinematic split lighting",
                    "description": "[SHOCK]",
                    "format_type": "WHO_WINS",
                },
                {
                    "script": "다음 상대는 은하다.",
                    "prompt": "cosmic challenger tease",
                    "description": "[LOOP]",
                    "format_type": "WHO_WINS",
                },
            ],
            "topic_folder",
            "우주대전 EP2",
            ["우주대전"],
            "desc",
            "",
        )

    monkeypatch.setattr(cutter_module, "generate_cuts", fake_generate_cuts)
    ctx = AgentContext(
        topic="태양 vs 블랙홀",
        language="ko",
        channel="askanything",
        format_type="WHO_WINS",
        series_title="우주대전",
    )
    agent = ScriptAgent(ModelRouter(), TokenTracker(ctx))

    async def run_agent():
        return [msg async for msg in agent.execute(ctx)]

    messages = asyncio.run(run_agent())

    assert captured["format_type"] == "WHO_WINS"
    assert captured["series_title"] == "우주대전"
    assert "continuity_rule" in captured["series_context"]
    assert "current_topic: 태양 vs 블랙홀" in captured["series_context"]
    assert ctx.title == "우주대전 EP2"
    assert any("기획 완료" in msg for msg in messages)
