"""
LLM-классификатор входящих запросов пользователей

Классифицирует сообщения на 4 категории:
- greeting: приветствие
- help_request: просьба о помощи
- off_topic: не относится к АН
- an_question: вопрос по теме АН (запускать RAG)
"""

import re
from enum import Enum
from typing import Optional
from loguru import logger

from src.llm.base import LLMClient
from src.utils.logging import trace, log_call_flow


class QueryCategory(str, Enum):
    """Категории пользовательских запросов"""
    GREETING = "greeting"
    HELP_REQUEST = "help_request"
    OFF_TOPIC = "off_topic"
    AN_QUESTION = "an_question"


CLASSIFIER_PROMPT = """Классифицируй запрос пользователя в одну из категорий:
- greeting: приветствие (привет, здравствуй, добрый день, и т.д.)
- help_request: просьба о помощи (помогите, нужна помощь, как бросить, и т.д.)
- off_topic: не относится к АН и выздоровлению (погода, новости, рецепты, и т.д.)
- an_question: вопрос по теме АН и выздоровлению (запускать RAG)

Ответь ТОЛЬКО названием категории без пояснений.

Запрос: "{query}"
"""


class QueryClassifier:
    """Классификатор запросов на основе LLM"""

    def __init__(self, llm_client: LLMClient, temperature: float = 0.1):
        """
        Инициализация классификатора

        Args:
            llm_client: LLM клиент для классификации
            temperature: Температура генерации (низкая для стабильности)
        """
        self._llm_client = llm_client
        self._temperature = temperature

    @trace(show_result=True)
    def classify(self, query: str) -> QueryCategory:
        """
        Классифицировать запрос пользователя

        Args:
            query: Текст сообщения пользователя

        Returns:
            Категория запроса
        """
        log_call_flow(f"Classifying query: '{query[:50]}...'")

        prompt = CLASSIFIER_PROMPT.format(query=query)

        try:
            response = self._llm_client.ask(
                question=prompt,
                context=None,
                sources=None,
                conversation_history=None,
            )

            # Очищаем ответ: удаляем все не-буквенные символы и приводим к lowercase
            # Это нужно т.к. LLM может возвращать ответ с пробелами, \n, \t и т.д.
            category_str = re.sub(r'[^a-zA-Z_]', '', response).lower()

            # Маппинг возможных вариантов ответа
            category_mapping = {
                "greeting": QueryCategory.GREETING,
                "help_request": QueryCategory.HELP_REQUEST,
                "off_topic": QueryCategory.OFF_TOPIC,
                "an_question": QueryCategory.AN_QUESTION,
            }

            category = category_mapping.get(category_str, QueryCategory.AN_QUESTION)
            log_call_flow(f"Query classified as: {category.value}")
            return category

        except Exception as e:
            logger.error(f"Classification error: {e}")
            # При ошибке классификации — запускаем RAG (безопасный fallback)
            return QueryCategory.AN_QUESTION


# Глобальный экземпляр (создаётся при импорте)
_classifier: Optional[QueryClassifier] = None


def get_classifier(llm_client: LLMClient) -> QueryClassifier:
    """Получить или создать классификатор"""
    global _classifier
    if _classifier is None:
        _classifier = QueryClassifier(llm_client)
    return _classifier


def classify_query(llm_client: LLMClient, query: str) -> QueryCategory:
    """
    Классифицировать запрос (удобная функция)

    Args:
        llm_client: LLM клиент
        query: Текст сообщения пользователя

    Returns:
        Категория запроса
    """
    classifier = get_classifier(llm_client)
    return classifier.classify(query)
