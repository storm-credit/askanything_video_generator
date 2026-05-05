from datetime import datetime

import pytest

from modules.scheduler.auto_deploy import _merge_youtube_tag_candidates
from modules.scheduler.time_planner import KST, calculate_schedule
from modules.upload.youtube.upload import _prepare_youtube_metadata
from modules.utils.channel_config import choose_channel_upload_title
from modules.utils.obsidian_parser import parse_day_file


def test_youtube_metadata_appends_public_hashtag_footer():
    description, tags = _prepare_youtube_metadata(
        "귀여워 보이지만, 사실은 생존을 위한 약속입니다. #OldTag #Shorts",
        ["#해달", "#동물", "#심해", "#생존전략"],
    )

    assert tags == ["해달", "동물", "심해", "생존전략", "OldTag"]
    assert description.endswith("#해달 #동물 #심해 #생존전략 #OldTag")
    assert "#Shorts" not in description
    assert description.count("#") == 5


def test_youtube_metadata_requires_at_least_five_tags_and_trims_extras():
    with pytest.raises(ValueError, match="정확히 5개"):
        _prepare_youtube_metadata(
            "Why sea otters hold hands while sleeping.\n\n#SeaOtter #OceanLife",
            [],
        )

    description, tags = _prepare_youtube_metadata(
        "귀여워 보이지만, 사실은 생존을 위한 약속입니다.",
        ["#해달", "#동물", "#심해", "#생존전략", "#과학", "#초과태그"],
    )
    assert tags == ["해달", "동물", "심해", "생존전략", "과학"]
    assert "#초과태그" not in description


def test_youtube_metadata_trims_day_and_preview_tag_union_to_five():
    description, tags = _prepare_youtube_metadata(
        "Sharks do not hunt humans like movies say.",
        [
            "#Sharks #Ocean #Animals #Myth #Science",
            "#Predators",
            "#Nature",
        ],
    )

    assert tags == ["Sharks", "Ocean", "Animals", "Myth", "Science"]
    assert description.count("#") == 5
    assert "#Predators" not in description


def test_auto_deploy_keeps_day_metadata_tags_to_five_before_upload():
    tags = _merge_youtube_tag_candidates(
        "#Sharks #Ocean #Animals #Myth #Science",
        ["#Predators", "#Nature", "#OceanTruth", "#ScienceFacts"],
    )

    assert tags == ["Sharks", "Ocean", "Animals", "Myth", "Science"]


def test_auto_deploy_preview_tags_only_fill_missing_metadata_slots():
    tags = _merge_youtube_tag_candidates(
        "#Sharks #Ocean #Animals",
        ["#Myth", "#Science", "#Predators"],
    )

    assert tags == ["Sharks", "Ocean", "Animals", "Myth", "Science"]


def test_schedule_keeps_day_file_public_metadata():
    schedule = calculate_schedule(
        [{
            "topic_group": "해달이 손잡고 자는 이유",
            "format_type": "FACT",
            "channels": {
                "askanything": {
                    "title": "해달이 손잡고 자는 진짜 이유",
                    "description": "귀여워 보이지만, 사실은 생존을 위한 약속입니다.",
                    "hashtags": "#해달 #동물 #심해 #생존전략 #과학",
                },
            },
        }],
        datetime(2026, 5, 1, tzinfo=KST),
        apply_rollout_strategy=False,
    )

    assert schedule[0]["title"] == "해달이 손잡고 자는 진짜 이유"
    assert schedule[0]["description"] == "귀여워 보이지만, 사실은 생존을 위한 약속입니다."
    assert schedule[0]["hashtags"] == "#해달 #동물 #심해 #생존전략 #과학"


def test_schedule_uses_channel_title_as_non_korean_llm_anchor_without_source_topic():
    schedule = calculate_schedule(
        [{
            "topic_group": "네 몸의 철은 죽은 별에서 왔다",
            "format_type": "FACT",
            "channels": {
                "wonderdrop": {
                    "title": "Dead Stars Made Your Blood",
                    "description": "The iron in your blood was forged inside dead stars.",
                    "hashtags": "#Science #Space #Stars #HumanBody #Cosmos",
                },
            },
        }],
        datetime(2026, 5, 1, tzinfo=KST),
        apply_rollout_strategy=False,
    )

    assert schedule[0]["_llm_topic_override"] == "Dead Stars Made Your Blood"


def test_parse_day_file_uses_channel_title_as_non_korean_llm_anchor(tmp_path):
    day_file = tmp_path / "Day 1 (5-1).md"
    day_file.write_text(
        """# Day 1 (5-1)

## 1. 네 몸의 철은 죽은 별에서 왔다 [공통] [시의성] [포맷:FACT]
> 근거: [카테고리: 교과서] - 별의 핵합성
> 검색 키워드: "iron in blood stars nucleosynthesis"

### askanything (ko)
제목: 네 몸의 철은 별이었다
설명: 몸속 철의 기원을 짧게 보여줍니다.
해시태그: #과학 #우주 #별 #인체 #철

### wonderdrop (en)
Title: Dead Stars Made Your Blood
Description: The iron in your blood was forged inside dead stars.
Hashtags: #Science #Space #Stars #HumanBody #Cosmos
""",
        encoding="utf-8",
    )

    jobs = parse_day_file(str(day_file))
    by_channel = {job["channel"]: job for job in jobs}

    assert by_channel["askanything"]["_llm_topic_override"] == "네 몸의 철은 죽은 별에서 왔다"
    assert by_channel["wonderdrop"]["_llm_topic_override"] == "Dead Stars Made Your Blood"


def test_upload_title_guard_falls_back_to_preview_title_for_weak_day_title():
    title, audit = choose_channel_upload_title(
        "wonderdrop",
        "The Secret",
        "Dead Stars Made Your Blood",
        "네 몸의 철은 죽은 별에서 왔다",
        "FACT",
    )

    assert title == "Dead Stars Made Your Blood"
    assert audit
