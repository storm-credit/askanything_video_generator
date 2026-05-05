import json
from pathlib import Path

from modules.scheduler.topic_generator import _collect_generation_validation
from modules.utils import series_state


def test_extract_next_matchup_from_final_cut_teaser():
    cuts = [
        {"script": "그래서 이번 승자는, 조직력의 로마 군단이야.", "format_type": "WHO_WINS"},
        {"script": "다음엔 바이킹이랑 스파르타가 붙으면 누가 이길까?", "format_type": "WHO_WINS"},
    ]

    assert series_state.extract_next_matchup_from_cuts(cuts) == "바이킹 vs 스파르타"


def test_record_who_wins_episode_persists_next_matchup(tmp_path, monkeypatch):
    monkeypatch.setattr(series_state, "SERIES_DIR", tmp_path)

    result = series_state.record_who_wins_episode(
        series_title="최강역사대전",
        topic="고대 로마 군단과 중세 기사 가상 대결",
        title="로마 군단 vs 중세 기사, 진짜 붙으면 누가 이길까?",
        cuts=[
            {"script": "로마 군단 대 중세 기사, 진짜 싸우면 누가 이길까?", "format_type": "WHO_WINS"},
            {"script": "그래서 이번 승자는, 조직력의 로마 군단이야.", "format_type": "WHO_WINS"},
            {"script": "다음엔 바이킹이랑 스파르타가 붙으면 누가 이길까?", "format_type": "WHO_WINS"},
        ],
        channel="askanything",
        video_url="https://youtube.com/shorts/FsAgFUZUXVU",
        publish_at="2026-05-03T13:00:00+00:00",
        task_date="2026-05-03",
        source_file="Day 33 (5-3).md",
        format_type="WHO_WINS",
    )

    assert result is not None
    path = Path(result["path"])
    payload = json.loads(path.read_text(encoding="utf-8"))
    runtime = payload["runtime"]

    assert payload["series_title"] == "최강역사대전"
    assert runtime["last_matchup"] == "로마 군단 vs 중세 기사"
    assert runtime["last_winner"] == "로마 군단"
    assert runtime["next_matchup"] == "바이킹 vs 스파르타"
    assert runtime["episodes"][0]["youtube_url"] == "https://youtube.com/shorts/FsAgFUZUXVU"


def test_active_series_context_marks_uploaded_teaser_as_required(tmp_path, monkeypatch):
    monkeypatch.setattr(series_state, "SERIES_DIR", tmp_path)
    series_state.record_who_wins_episode(
        series_title="최강역사대전",
        topic="로마 군단 vs 중세 기사",
        title="로마 군단 vs 중세 기사",
        cuts=[
            {"script": "승자는 로마 군단.", "format_type": "WHO_WINS"},
            {"script": "다음엔 바이킹이랑 스파르타가 붙으면 누가 이길까?", "format_type": "WHO_WINS"},
        ],
        channel="askanything",
        format_type="WHO_WINS",
    )

    context = series_state.build_active_series_context()

    assert "[필수 후속 VS]" in context
    assert "[시리즈:최강역사대전]" in context
    assert "바이킹 vs 스파르타" in context
    assert "반드시 다음 Day 후보" in context


def test_generation_validation_rejects_single_who_wins_without_series_tag():
    raw_content = """# Day 40 (5-10)

## 1. ⚔️ 바이킹 vs 스파르타 [공통] [시의성] [포맷:WHO_WINS]
> 근거: [카테고리: 역사/문명] — 전투 방식 비교
> 검색 키워드: "viking warrior vs spartan hoplite tactics"
> 채널: askanything
> 핵심 훅: 누가 이길까?
> 훅 패턴: ⑥ 대비/비교

## 2. 🌌 달이 사라진다면 [공통] [포맷:IF]
## 3. 🐋 심해 소리의 정체 [공통] [채널분화] [포맷:MYSTERY]
"""

    _warnings, hard_errors = _collect_generation_validation(raw_content, [], ["Day 40 (5-10)"])

    assert any("WHO_WINS 시리즈 태그 누락" in error for error in hard_errors)


def test_generation_validation_requires_teased_followup():
    active_context = """## VS 시리즈 연속성 상태
[필수 후속 VS]
- [시리즈:최강역사대전] 다음 에피소드 EP2: 바이킹 vs 스파르타. 이전편: 로마 군단 vs 중세 기사. 이전 승자: 로마 군단. 반드시 다음 Day 후보에 [포맷:WHO_WINS]로 편성.
"""
    raw_content = """# Day 40 (5-10)

## 1. 🌌 태양 vs 블랙홀 [공통] [시의성] [포맷:WHO_WINS] [시리즈:최강우주대전]
> 근거: [카테고리: 우주/행성] — 중력 비교
> 검색 키워드: "sun vs black hole gravity"
> 채널: askanything
> 핵심 훅: 누가 이길까?
> 훅 패턴: ⑥ 대비/비교

## 2. 🌕 달이 사라진다면 [공통] [포맷:IF]
## 3. 🐋 심해 소리의 정체 [공통] [채널분화] [포맷:MYSTERY]
"""

    _warnings, hard_errors = _collect_generation_validation(
        raw_content,
        [],
        ["Day 40 (5-10)"],
        active_context,
    )

    assert any("필수 VS 후속 시리즈 누락" in error for error in hard_errors)
