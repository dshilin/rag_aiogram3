from abc import ABC, abstractmethod
from typing import Optional, List


# Системный промт для ИИ-агента АН
SYSTEM_PROMPT_AN = """Ты — ИИ-агент, основанный на литературе сообщества Анонимных Наркоманов (АН).
Твоя задача — отвечать пользователю исключительно в рамках официальной литературы АН.

Правила:
Используй только следующие источники:
- Базовый текст АН
- Ежедневник Только Сегодня
- Это работает – как и почему

В 80% случаев отвечай прямой цитатой, всегда указывая источник (например: «Базовый текст, стр. 25»).

В остальных случаях можешь:
- предложить пользователю задуматься над вопросом,
- сослаться на конкретную литературу, где он может найти ответ.

Агент не даёт советов от себя. Никаких личных интерпретаций или мнений.

Если вопрос не касается АН или выздоровления — откажись отвечать.

Если пользователь просит о помощи, предложи ему посетить ближайшую группу АН и уточни местоположение.

Общение веди спокойным, нейтральным тоном, без излишней эмоциональности."""


class LLMClient(ABC):
    """Абстрактный базовый класс для LLM клиентов"""

    def __init__(
        self,
        model: str = "default",
        temperature: float = 0.3,
        max_tokens: int = 500,
        system_prompt: Optional[str] = None,
    ):
        """
        Инициализация LLM клиента

        Args:
            model: Название модели
            temperature: Температура генерации (0.0 - 1.0)
            max_tokens: Максимальное количество токенов в ответе
            system_prompt: Системный промт (по умолчанию используется SYSTEM_PROMPT_AN)
        """
        self._model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt or SYSTEM_PROMPT_AN

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Название провайдера (например, 'yandex', 'vsegpt', 'openai')"""
        pass

    @abstractmethod
    def ask(
        self,
        question: str,
        context: Optional[str] = None,
        sources: Optional[List[str]] = None,
    ) -> str:
        """
        Отправить запрос к LLM

        Args:
            question: Вопрос пользователя
            context: Контекст из RAG (опционально)
            sources: Источники из RAG для цитирования (опционально)

        Returns:
            Текст ответа от модели или сообщение об ошибке
        """
        pass

    def _build_prompt(
        self,
        question: str,
        context: Optional[str] = None,
        sources: Optional[List[str]] = None,
    ) -> str:
        """
        Построить промпт с контекстом и источниками

        Args:
            question: Вопрос пользователя
            context: Контекст из RAG (опционально)
            sources: Источники для цитирования (опционально)

        Returns:
            Сформированный промпт
        """
        parts = []

        # Добавляем контекст
        if context:
            parts.append(f"Контекст из литературы АН:\n{context}\n")

        # Добавляем источники
        if sources:
            parts.append(f"Источники: {', '.join(sources)}\n")

        # Добавляем вопрос
        parts.append(f"Вопрос: {question}")

        return "\n\n".join(parts) if parts else question
