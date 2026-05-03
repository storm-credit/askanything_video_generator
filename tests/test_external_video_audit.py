import json

from PIL import Image

from modules.analytics import external_video_audit as audit


def test_parse_frame_times_uses_defaults_for_bad_input():
    assert audit._parse_frame_times("bad,,") == list(audit.DEFAULT_FRAME_TIMES)
    assert audit._parse_frame_times("0, .5, 1.25") == [0.0, 0.5, 1.25]


def test_parse_video_id_supports_shorts_watch_and_bare_id():
    assert audit._parse_video_id("https://www.youtube.com/shorts/o6vTOrB9zZQ") == "o6vTOrB9zZQ"
    assert audit._parse_video_id("https://www.youtube.com/watch?v=o6vTOrB9zZQ") == "o6vTOrB9zZQ"
    assert audit._parse_video_id("o6vTOrB9zZQ") == "o6vTOrB9zZQ"


def test_extract_signal_url_reads_notes_json():
    row = {"notes": json.dumps({"url": "https://www.youtube.com/shorts/o6vTOrB9zZQ"})}
    assert audit._extract_signal_url(row) == "https://www.youtube.com/shorts/o6vTOrB9zZQ"
    assert audit._extract_signal_url({"notes": "not json"}) is None


def test_contact_sheet_and_metrics_from_frames(tmp_path):
    frame_a = tmp_path / "frame_0000ms.jpg"
    frame_b = tmp_path / "frame_0500ms.jpg"
    Image.new("RGB", (360, 640), (10, 10, 10)).save(frame_a)
    Image.new("RGB", (360, 640), (245, 245, 245)).save(frame_b)

    output = audit.make_contact_sheet([frame_a, frame_b], tmp_path / "sheet.jpg", title="Example")
    metrics = audit.summarize_visual_metrics([frame_a, frame_b])

    assert output and output.exists()
    assert "vertical_9_16" in metrics["tags"]
    assert metrics["motion"]["pace"] == "fast"


def test_format_section_time_for_ytdlp_ranges():
    assert audit._format_section_time(0) == "0:00:00"
    assert audit._format_section_time(5) == "0:00:05"
    assert audit._format_section_time(5.5) == "0:00:05.5"
