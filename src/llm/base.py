from abc import ABC, abstractmethod
from typing import Optional


class LLMClient(ABC):
    """Абстрактный базовый класс для LLM клиентов"""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Название провайдера (например, 'yandex', 'vsegpt', 'openai')"""
        pass

    @abstractmethod
    def ask(self, question: str, context: Optional[str] = None) -> str:
        """
        Отправить запрос к LLM

        Args:
            question: Вопрос пользователя
            context: Контекст из RAG (опционально)

        Returns:
            Текст ответа от модели или сообщение об ошибке
        """
        pass

    def _build_prompt(self, question: str, context: Optional[str] = None) -> str:
        """
        Построить промпт с контекстом

        Args:
            question: Вопрос пользователя
            context: Контекст из RAG (опционально)

        Returns:
            Сформированный промпт
        """
        if context:
            return (
                f"Используй следующий контекст для ответа на вопрос:\n\n"
                f"Контекст:\n{context}\n\n"
                f"Вопрос: {question}\n\n"
                f"Ответ:"
            )
        return question
