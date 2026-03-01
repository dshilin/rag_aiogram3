import pytest
from unittest.mock import Mock, patch

from src.bot.classifier import QueryClassifier, QueryCategory, CLASSIFIER_PROMPT


class TestQueryCategory:
    """Тесты enum категорий запросов"""

    def test_greeting_category(self):
        assert QueryCategory.GREETING.value == "greeting"

    def test_help_request_category(self):
        assert QueryCategory.HELP_REQUEST.value == "help_request"

    def test_off_topic_category(self):
        assert QueryCategory.OFF_TOPIC.value == "off_topic"

    def test_an_question_category(self):
        assert QueryCategory.AN_QUESTION.value == "an_question"


class TestQueryClassifier:
    """Тесты классификатора запросов"""

    def test_classifier_initialization(self):
        """Проверка инициализации классификатора"""
        mock_llm = Mock()
        classifier = QueryClassifier(mock_llm, temperature=0.1)

        assert classifier._llm_client == mock_llm
        assert classifier._temperature == 0.1

    def test_classifier_default_temperature(self):
        """Проверка температуры по умолчанию"""
        mock_llm = Mock()
        classifier = QueryClassifier(mock_llm)

        assert classifier._temperature == 0.1

    def test_classify_greeting(self):
        """Классификация приветствия"""
        mock_llm = Mock()
        mock_llm.ask.return_value = "greeting"

        classifier = QueryClassifier(mock_llm)
        result = classifier.classify("Привет!")

        assert result == QueryCategory.GREETING
        mock_llm.ask.assert_called_once()

    def test_classify_help_request(self):
        """Классификация просьбы о помощи"""
        mock_llm = Mock()
        mock_llm.ask.return_value = "help_request"

        classifier = QueryClassifier(mock_llm)
        result = classifier.classify("Помогите мне!")

        assert result == QueryCategory.HELP_REQUEST

    def test_classify_off_topic(self):
        """Классификация темы не относящейся к АН"""
        mock_llm = Mock()
        mock_llm.ask.return_value = "off_topic"

        classifier = QueryClassifier(mock_llm)
        result = classifier.classify("Какой сегодня прогноз погоды?")

        assert result == QueryCategory.OFF_TOPIC

    def test_classify_an_question(self):
        """Классификация вопроса по теме АН"""
        mock_llm = Mock()
        mock_llm.ask.return_value = "an_question"

        classifier = QueryClassifier(mock_llm)
        result = classifier.classify("Что такое шаги выздоровления?")

        assert result == QueryCategory.AN_QUESTION

    def test_classify_case_insensitive(self):
        """Проверка регистронезависимости ответа"""
        mock_llm = Mock()
        mock_llm.ask.return_value = "GREETING"  # верхний регистр

        classifier = QueryClassifier(mock_llm)
        result = classifier.classify("Здравствуй!")

        assert result == QueryCategory.GREETING

    def test_classify_unknown_returns_an_question(self):
        """Неизвестная категория возвращает AN_QUESTION (fallback)"""
        mock_llm = Mock()
        mock_llm.ask.return_value = "unknown_category"

        classifier = QueryClassifier(mock_llm)
        result = classifier.classify("Тест")

        assert result == QueryCategory.AN_QUESTION

    def test_classify_error_returns_an_question(self):
        """Ошибка классификации возвращает AN_QUESTION (fallback)"""
        mock_llm = Mock()
        mock_llm.ask.side_effect = Exception("API error")

        classifier = QueryClassifier(mock_llm)
        result = classifier.classify("Тест")

        assert result == QueryCategory.AN_QUESTION

    def test_classify_strips_whitespace_and_newlines(self):
        """Проверка что ответ очищается от пробелов и переносов строк"""
        mock_llm = Mock()
        mock_llm.ask.return_value = "greeting\n  "

        classifier = QueryClassifier(mock_llm)
        result = classifier.classify("Привет!")

        assert result == QueryCategory.GREETING

    def test_classify_handles_response_with_extra_chars(self):
        """Проверка что ответ обрабатывается даже с лишними символами"""
        mock_llm = Mock()
        mock_llm.ask.return_value = "  off_topic\t\n"

        classifier = QueryClassifier(mock_llm)
        result = classifier.classify("Какой рецепт борща?")

        assert result == QueryCategory.OFF_TOPIC

    def test_classify_builds_correct_prompt(self):
        """Проверка формирования промпта"""
        mock_llm = Mock()
        mock_llm.ask.return_value = "greeting"

        classifier = QueryClassifier(mock_llm)
        classifier.classify("Привет!")

        call_args = mock_llm.ask.call_args
        question_arg = call_args[1]['question']

        assert "Привет!" in question_arg
        assert "Классифицируй запрос пользователя" in question_arg

    def test_classify_calls_llm_with_none_context(self):
        """Проверка что context и sources передаются как None"""
        mock_llm = Mock()
        mock_llm.ask.return_value = "greeting"

        classifier = QueryClassifier(mock_llm)
        classifier.classify("Тест")

        call_kwargs = mock_llm.ask.call_args[1]
        assert call_kwargs['context'] is None
        assert call_kwargs['sources'] is None
        assert call_kwargs['conversation_history'] is None


class TestClassifyQueryFunction:
    """Тесты функции classify_query"""

    def test_classify_query_uses_singleton(self):
        """Проверка что classify_query использует singleton"""
        from src.bot.classifier import classify_query, _classifier

        mock_llm = Mock()
        mock_llm.ask.return_value = "greeting"

        # Сбрасываем singleton
        import src.bot.classifier as classifier_module
        classifier_module._classifier = None

        result = classify_query(mock_llm, "Привет!")

        assert result == QueryCategory.GREETING
        assert classifier_module._classifier is not None

    def test_classify_query_reuses_singleton(self):
        """Проверка что singleton переиспользуется"""
        import src.bot.classifier as classifier_module
        from src.bot.classifier import classify_query

        mock_llm = Mock()
        mock_llm.ask.return_value = "greeting"

        # Устанавливаем singleton
        classifier_module._classifier = QueryClassifier(mock_llm)
        first = classifier_module._classifier

        result = classify_query(mock_llm, "Тест")

        assert classifier_module._classifier is first


class TestClassifierPrompts:
    """Тесты промптов классификатора"""

    def test_classifier_prompt_contains_categories(self):
        """Проверка что промпт содержит все категории"""
        assert "greeting" in CLASSIFIER_PROMPT
        assert "help_request" in CLASSIFIER_PROMPT
        assert "off_topic" in CLASSIFIER_PROMPT
        assert "an_question" in CLASSIFIER_PROMPT

    def test_classifier_prompt_requires_single_word_response(self):
        """Проверка что промпт требует только название категории"""
        assert "ТОЛЬКО названием категории" in CLASSIFIER_PROMPT
        assert "без пояснений" in CLASSIFIER_PROMPT

    def test_classifier_prompt_has_query_placeholder(self):
        """Проверка что промпт имеет плейсхолдер для запроса"""
        assert "{query}" in CLASSIFIER_PROMPT
