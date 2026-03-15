"""slugify_topic / _safe_slug 유닛 테스트"""
from modules.utils.slugify import _safe_slug, slugify_topic


class TestSafeSlug:
    def test_basic_english(self):
        assert _safe_slug("hello world", max_len=30) == "hello_world"

    def test_removes_special_chars(self):
        assert _safe_slug("hello!@#$%world", max_len=30) == "helloworld"

    def test_collapses_underscores(self):
        assert _safe_slug("a   b   c", max_len=30) == "a_b_c"

    def test_strips_leading_trailing(self):
        assert _safe_slug("  hello  ", max_len=30) == "hello"

    def test_max_len_truncation(self):
        result = _safe_slug("a" * 100, max_len=10)
        assert len(result) <= 10

    def test_empty_string_fallback(self):
        assert _safe_slug("", max_len=30) == "topic"

    def test_only_special_chars_fallback(self):
        assert _safe_slug("!@#$%", max_len=30) == "topic"

    def test_korean_preserved(self):
        result = _safe_slug("블랙홀 탐험", max_len=60)
        assert "블랙홀" in result
        assert "탐험" in result

    def test_mixed_content(self):
        result = _safe_slug("AI 기술 2024", max_len=60)
        assert "AI" in result


class TestSlugifyTopic:
    def test_english_topic(self):
        result = slugify_topic("Black Hole Adventure", lang="en")
        assert result == "black_hole_adventure"

    def test_english_max_len(self):
        result = slugify_topic("a" * 50, lang="en")
        assert len(result) <= 30

    def test_empty_topic(self):
        assert slugify_topic("", lang="en") == "topic"

    def test_none_topic(self):
        assert slugify_topic(None, lang="en") == "topic"

    def test_whitespace_topic(self):
        assert slugify_topic("   ", lang="en") == "topic"

    def test_korean_returns_string(self):
        """konlpy 유무 관계없이 문자열 반환"""
        result = slugify_topic("블랙홀에 빠지면", lang="ko")
        assert isinstance(result, str)
        assert 0 < len(result) <= 60
