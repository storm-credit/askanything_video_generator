"""slugify_topic 유닛 테스트 — 한글/영어/특수문자 엣지케이스"""
import pytest
from unittest.mock import patch, MagicMock
from modules.utils.slugify import slugify_topic, _safe_slug


class TestSafeSlug:
    def test_basic(self):
        assert _safe_slug("hello world", max_len=30) == "hello_world"

    def test_special_chars_removed(self):
        assert _safe_slug("hello!@#$%world", max_len=30) == "helloworld"

    def test_multiple_spaces(self):
        assert _safe_slug("hello   world", max_len=30) == "hello_world"

    def test_max_len_truncation(self):
        result = _safe_slug("a" * 100, max_len=10)
        assert len(result) <= 10

    def test_empty_string(self):
        assert _safe_slug("", max_len=30) == "topic"

    def test_only_special_chars(self):
        assert _safe_slug("!@#$%", max_len=30) == "topic"

    def test_korean_preserved(self):
        result = _safe_slug("블랙홀_우주", max_len=60)
        assert "블랙홀" in result

    def test_leading_trailing_underscores_stripped(self):
        assert _safe_slug("_hello_", max_len=30) == "hello"


class TestSlugifyTopic:
    def test_english_lowercase(self):
        result = slugify_topic("Black Hole Survival", lang="en")
        assert result == "black_hole_survival"

    def test_english_max_len(self):
        result = slugify_topic("A" * 50, lang="en")
        assert len(result) <= 30

    def test_empty_topic(self):
        result = slugify_topic("", lang="en")
        assert result == "topic"

    def test_none_topic(self):
        result = slugify_topic(None, lang="en")
        assert result == "topic"

    def test_whitespace_only(self):
        result = slugify_topic("   ", lang="en")
        assert result == "topic"

    def test_korean_with_okt_failure(self):
        """Okt 형태소 분석기 없을 때 원문 폴백"""
        with patch("modules.utils.slugify._get_okt", side_effect=Exception("JVM not found")):
            result = slugify_topic("블랙홀 생존 시나리오", lang="ko")
            assert len(result) > 0
            assert len(result) <= 60

    def test_korean_with_mock_okt(self):
        """Okt가 명사를 추출할 때"""
        mock_okt = MagicMock()
        mock_okt.nouns.return_value = ["블랙홀", "생존"]
        with patch("modules.utils.slugify._get_okt", return_value=mock_okt):
            result = slugify_topic("블랙홀 생존 시나리오", lang="ko")
            assert "블랙홀" in result
            assert "생존" in result

    def test_korean_okt_no_nouns(self):
        """Okt가 명사를 찾지 못할 때 원문 사용"""
        mock_okt = MagicMock()
        mock_okt.nouns.return_value = []
        with patch("modules.utils.slugify._get_okt", return_value=mock_okt):
            result = slugify_topic("ㅋㅋㅋ", lang="ko")
            assert len(result) > 0
