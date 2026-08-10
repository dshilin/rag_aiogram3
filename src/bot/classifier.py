"""
LLM-классификатор входящих запросов пользователей

Классифицирует сообщения на 4 категории:
- greeting: приветствие
- help_request: просьба о помощи
- off_topic: не относится к АН
- an_question: вопрос по теме АН (запускать RAG)
"""

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


CLASSIFIER_SYSTEM_PROMPT = "Ты — классификатор запросов. Отвечай ТОЛЬКО названием категории, без пояснений."

CLASSIFIER_PROMPT = """Классифицируй запрос пользователя в одну из категорий:

- greeting: приветствие (привет, здравствуй, добрый день, и т.д.)
- help_request: просьба о помощи (помогите, нужна помощь, как бросить, и т.д.)
- off_topic: не относится к теме АН (Анонимные Наркоманы) и выздоровлению
  (например: погода, новости, рецепты, программирование, учёба, работа, хобби)
- an_question: вопрос по теме АН и выздоровлению — запускать RAG
  (например: "третья традиция", "12 шагов", "первый шаг", "что такое бессилие",
  "спонсорство", "принципы", "Базовый текст АН", "как работают собрания")

Если запрос короткий и упоминает тему, связанную с АН (шаги, традиции, выздоровление,
зависимость, собрания) — это an_question.

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

    @trace
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
                system_prompt=CLASSIFIER_SYSTEM_PROMPT,
            )

            # Берём только первую строку ответа LLM
            # (YandexGPT часто добавляет пояснения с новых строк)
            first_line = response.strip().split('\n')[0].strip().lower().rstrip('.,!?;:')
            
            if first_line in ("greeting", "help_request", "off_topic", "an_question"):
                category = QueryCategory(first_line)
                log_call_flow(f"Query classified as: {category.value}")
                return category

            log_call_flow(f"No valid category in first line ('{first_line}'), using fallback")
            return QueryCategory.AN_QUESTION

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
