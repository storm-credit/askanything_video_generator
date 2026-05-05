from modules.gpt.cutter.quality import _validate_hard_fail
from modules.orchestrator.base import AgentContext, ModelRouter
from modules.orchestrator.orchestrator import MainOrchestrator
from modules.orchestrator.tracker import TokenTracker


def _cut(script: str, tag: str, fmt: str) -> dict:
    return {
        "script": script,
        "description": f"[{tag}]",
        "prompt": "dramatic contrast, cinematic vertical composition, sharp subject",
        "format_type": fmt,
        "topic": "format gate test",
        "topic_title": "format gate test",
    }


def test_fact_numbers_density_is_soft_guard_not_code_hard_fail():
    cuts = [
        _cut("Mars has 2 moons and a hidden storm", "SHOCK", "FACT"),
        _cut("Phobos keeps silent pressure over the rocks", "WONDER", "FACT"),
        _cut("The archive names Olympus Mons without a scale", "TENSION", "FACT"),
        _cut("A rover crossed 7 meters over buried ice", "TENSION", "FACT"),
        _cut("Dust lifted 20 kilometers above valleys", "TENSION", "FACT"),
        _cut("The reveal lands at 4 billion years", "REVEAL", "FACT"),
        _cut("A red canyon keeps another ancient clue", "IDENTITY", "FACT"),
        _cut("The next planet keeps 3 deeper scars", "LOOP", "FACT"),
    ]

    failures = _validate_hard_fail(cuts)

    assert not any(f.startswith("FORMAT_FACT: 수치 없는 컷") for f in failures)


def test_scale_numbers_prompt_hard_fail_is_code_hard_fail():
    cuts = [
        _cut("A 1 centimeter bead dwarfs the city", "SHOCK", "SCALE"),
        _cut("A familiar coin becomes the first anchor", "WONDER", "SCALE"),
        _cut("The model jumps 100 times past a stadium", "TENSION", "SCALE"),
        _cut("A mountain shrinks beside 8 planets", "DISBELIEF", "SCALE"),
        _cut("One silent ocean fills the frame", "SHOCK", "SCALE"),
        _cut("The twist reaches 1000000 meters of scale", "REVEAL", "SCALE"),
        _cut("Another comparison opens at 10 billion steps", "LOOP", "SCALE"),
    ]

    failures = _validate_hard_fail(cuts)

    assert any(f.startswith("FORMAT_SCALE: 수치/배율 없는 컷 2개") for f in failures)


def test_paradox_double_reversal_prompt_hard_fail_is_code_hard_fail():
    cuts = [
        _cut("The obvious answer feels safe at first", "SHOCK", "PARADOX"),
        _cut("The common belief looks convincing today", "WONDER", "PARADOX"),
        _cut("But the first crack appears in the data", "TENSION", "PARADOX"),
        _cut("One reversal changes the whole frame", "DISBELIEF", "PARADOX"),
        _cut("A second clue raises the stakes again", "TENSION", "PARADOX"),
        _cut("The personal angle lands quietly", "IDENTITY", "PARADOX"),
        _cut("The old belief now feels unstable", "WONDER", "PARADOX"),
        _cut("Another twist waits behind this one", "LOOP", "PARADOX"),
    ]

    failures = _validate_hard_fail(cuts)

    assert any(f.startswith("FORMAT_PARADOX: 반전 1개") for f in failures)


def test_image_validation_retry_invalidates_cache_and_bypasses_cache(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace

    from modules.orchestrator.agents import image_validator
    from modules.utils.constants import MASTER_STYLE
    import modules.utils.cache as cache_module
    import modules.utils.keys as keys_module

    prompt = "a clear moon crater, no text"
    new_image = tmp_path / "new.png"
    new_image.write_bytes(b"x" * 6000)
    validations = [
        {"pass": False, "reason": "text in image", "score": 3},
        {"pass": True, "reason": "clean", "score": 9},
    ]
    calls = {}
    invalidated = []

    monkeypatch.setattr(image_validator, "validate_image", lambda *args, **kwargs: validations.pop(0))
    monkeypatch.setattr(keys_module, "get_google_key", lambda *args, **kwargs: "test-key")
    monkeypatch.setattr(cache_module, "invalidate_cache", lambda key: invalidated.append(key))

    def fake_generate_image_imagen(*args, **kwargs):
        calls["skip_cache"] = kwargs.get("skip_cache")
        return str(new_image)

    monkeypatch.setitem(
        sys.modules,
        "modules.image.imagen",
        SimpleNamespace(generate_image_imagen=fake_generate_image_imagen),
    )

    result = image_validator.validate_and_retry(
        "old.png",
        prompt,
        0,
        "topic",
        api_key="test-key",
        image_engine="imagen",
    )

    assert result == str(new_image)
    assert calls["skip_cache"] is True
    assert invalidated == [MASTER_STYLE + prompt]


def test_post_asset_gate_fails_when_removed_cut_breaks_format_count():
    cuts = [
        _cut("Cut 1 has 1 concrete number", "SHOCK", "FACT"),
        _cut("Cut 2 has 2 concrete numbers", "WONDER", "FACT"),
        _cut("Cut 3 has 3 concrete numbers", "TENSION", "FACT"),
        _cut("Cut 4 has 4 concrete numbers", "TENSION", "FACT"),
        _cut("Cut 5 has 5 concrete numbers", "TENSION", "FACT"),
        _cut("Cut 6 has 6 concrete numbers", "REVEAL", "FACT"),
        _cut("Cut 7 has 7 concrete numbers", "LOOP", "FACT"),
    ]
    ctx = AgentContext(topic="post asset gate", channel="wonderdrop", format_type="FACT", cuts=cuts)

    failures = MainOrchestrator._validate_post_asset_cuts(ctx)

    assert any(f.startswith("FORMAT_CUT_COUNT_AFTER_ASSET: FACT 7컷") for f in failures)


def test_quality_agent_runs_structure_fact_and_subject_layers(monkeypatch):
    import asyncio

    import modules.gpt.cutter as cutter_module
    import modules.gpt.cutter.generator as generator_module
    import modules.utils.keys as keys_module
    from modules.orchestrator.agents.quality import QualityAgent

    calls = []

    def mark(name):
        def _inner(cuts, *args, **kwargs):
            calls.append(name)
            return cuts
        return _inner

    monkeypatch.setattr(keys_module, "get_google_key", lambda *args, **kwargs: "test-key")
    monkeypatch.setattr(generator_module, "_should_run_fact_verify", lambda *args, **kwargs: True)
    monkeypatch.setattr(cutter_module, "_verify_highness_structure", mark("structure"))
    monkeypatch.setattr(cutter_module, "_verify_facts", mark("facts"))
    monkeypatch.setattr(cutter_module, "_verify_subject_match", mark("subject"))

    cuts = [
        _cut(f"Cut {i} has {i} concrete numbers", "TENSION", "FACT")
        for i in range(1, 8)
    ]
    cuts[0]["description"] = "[SHOCK]"
    cuts[5]["description"] = "[REVEAL]"
    cuts[-1]["description"] = "[LOOP]"
    ctx = AgentContext(
        topic="quality topic",
        channel="wonderdrop",
        format_type="FACT",
        fact_context="verified reference facts",
        cuts=cuts,
        gemini_keys_override="test-key",
    )
    agent = QualityAgent(ModelRouter(), TokenTracker(ctx))

    async def run_agent():
        return [msg async for msg in agent.execute(ctx)]

    messages = asyncio.run(run_agent())

    assert calls == ["structure", "facts", "subject"]
    assert any("전문가 검증 시작" in msg for msg in messages)
    assert len(ctx.token_log) == 3


def test_cost_tracker_separates_cache_hits_and_qwen_chars(tmp_path, monkeypatch):
    from modules.utils import cost_tracker

    monkeypatch.setattr(cost_tracker, "_DAILY_FILE", str(tmp_path / "daily_cost.json"))

    entry = cost_tracker.record_generation_cost(
        channel="wonderdrop",
        success=True,
        llm_usd=0.01,
        image_count=2,
        image_cache_hits=3,
        tts_chars=0,
        qwen_tts_chars=1200,
        tts_engine_counts={"qwen3": 4},
    )
    daily = cost_tracker.get_daily_summary()

    assert entry["image_usd"] == cost_tracker.calc_image_cost(2)
    assert entry["tts_usd"] == 0
    assert daily["wonderdrop"]["image_cache_hits"] == 3
    assert daily["wonderdrop"]["qwen_tts_chars"] == 1200
    assert daily["wonderdrop"]["tts_engine_counts"]["qwen3"] == 4
