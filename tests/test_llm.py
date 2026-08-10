"""Tests for LLM base: prompt building, system prompt"""
import pytest

from src.llm.base import LLMClient, SYSTEM_PROMPT_AN


class FakeLLM(LLMClient):
    @property
    def provider_name(self) -> str:
        return "fake"

    def ask(self, question, context=None, sources=None, conversation_history=None):
        return self._build_prompt(question, context, sources, conversation_history)


class TestBuildPrompt:
    def test_question_only(self):
        client = FakeLLM()
        result = client.ask("Какой первый шаг?")
        assert "Вопрос: Какой первый шаг?" in result

    def test_context_included(self):
        client = FakeLLM()
        result = client.ask("Вопрос", context="Цитата из литературы.")
        assert "Контекст из литературы АН" in result
        assert "Цитата из литературы." in result

    def test_sources_listed(self):
        client = FakeLLM()
        result = client.ask(
            "Вопрос",
            context="Цитата.",
            sources=["Базовый текст АН (стр. 42)", "Ежедневник Январь (стр. 15)"],
        )
        assert "Доступные источники для цитирования" in result
        assert "Базовый текст АН (стр. 42)" in result
        assert "Ежедневник Январь (стр. 15)" in result

    def test_no_sources_when_not_provided(self):
        client = FakeLLM()
        result = client.ask("Вопрос", context="Цитата.")
        assert "Доступные источники" not in result

    def test_conversation_history_included(self):
        client = FakeLLM()
        history = [
            {"role": "user", "content": "Привет"},
            {"role": "assistant", "content": "Здравствуйте"},
        ]
        result = client.ask("Вопрос", conversation_history=history)
        assert "История диалога" in result
        assert "Пользователь: Привет" in result
        assert "Ассистент: Здравствуйте" in result


class TestSystemPrompt:
    def test_prompts_inline_citations(self):
        assert "После каждой цитаты обязательно укажи источник" in SYSTEM_PROMPT_AN
        assert "НЕ указывай" not in SYSTEM_PROMPT_AN
        assert "Используй ТОЛЬКО информацию из маркеров" in SYSTEM_PROMPT_AN

    def test_starts_with_required_phrase(self):
        assert "начинается с фразы" in SYSTEM_PROMPT_AN
        assert "В нашей литературе" in SYSTEM_PROMPT_AN
