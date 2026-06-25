"""Tests for src.utils.text"""

import pytest

from src.utils.text import _extract_keywords


class TestExtractKeywords:
    def test_extracts_nouns_from_russian_text(self):
        text = "Капитуляция выздоровление честность."
        result = _extract_keywords(text, top_n=3)
        assert len(result) <= 3
        assert "капитуляция" in result
        assert "выздоровление" in result
        assert "честность" in result

    def test_returns_empty_for_no_nouns(self):
        text = "и в на"
        result = _extract_keywords(text, top_n=5)
        assert result == []

    def test_respects_top_n(self):
        text = "Слон бегемот жираф собака кошка мышь."
        result = _extract_keywords(text, top_n=2)
        assert len(result) <= 2
