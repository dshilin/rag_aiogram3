"""
Клиент для работы с OpenAI API

Использует системный промт АН для генерации ответов на основе литературы
Анонимных Наркоманов.
"""

import os
from typing import Optional, List

from openai import OpenAI
from loguru import logger

from src.core.config import settings
from src.llm.base import LLMClient, SYSTEM_PROMPT_AN
from src.utils.logging import trace, log_call_flow


class OpenAIClient(LLMClient):
    """Клиент для работы с OpenAI API"""

    def __init__(
        self,
        model: str = "gpt-3.5-turbo",
        temperature: float = 0.3,
        max_tokens: int = 500,
        system_prompt: Optional[str] = None,
    ):
        """
        Инициализация клиента OpenAI

        Args:
            model: Название модели (например, gpt-3.5-turbo, gpt-4, и т.д.)
            temperature: Температура генерации (0.0 - 1.0)
            max_tokens: Максимальное количество токенов в ответе
            system_prompt: Системный промт (по умолчанию используется SYSTEM_PROMPT_AN)
        """
        super().__init__(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
        )

        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY не установлен в .env")

        self.client = OpenAI(api_key=settings.openai_api_key)
        self.api_url = "https://api.openai.com/v1/chat/completions"

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def model_name(self) -> str:
        return self._model

    @trace(show_result=False)
    def ask(
        self,
        question: str,
        context: Optional[str] = None,
        sources: Optional[List[str]] = None,
        conversation_history: Optional[List[dict]] = None,
    ) -> str:
        """
        Отправить запрос к OpenAI

        Args:
            question: Вопрос пользователя
            context: Контекст из RAG (опционально)
            sources: Источники из RAG для цитирования (опционально)
            conversation_history: История диалога для поддержания контекста (опционально)

        Returns:
            Текст ответа от модели или сообщение об ошибке
        """
        log_call_flow(f"OpenAI request: '{question[:50]}...' with context={context is not None}")

        # Формируем промпт с контекстом
        user_prompt = self._build_prompt(question, context, sources, conversation_history)
        log_call_flow(f"Built prompt: '{user_prompt[:50]}...'")

        try:
            log_call_flow(f"OpenAI API URL: {self.api_url}")
            log_call_flow(
                f"OpenAI request payload: model={self._model}, "
                f"temperature={self.temperature}, max_tokens={self.max_tokens}"
            )

            # Формируем сообщения для API
            messages = [{"role": "system", "content": self.system_prompt}]
            
            # Добавляем историю диалога, если есть
            if conversation_history:
                for msg in conversation_history:
                    messages.append({"role": msg["role"], "content": msg["content"]})
            
            # Добавляем текущий вопрос
            messages.append({"role": "user", "content": user_prompt})

            response = self.client.chat.completions.create(
                model=self._model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )

            answer = response.choices[0].message.content
            log_call_flow(f"OpenAI response received: '{answer[:50]}...'")
            return answer

        except Exception as e:
            logger.error(f"OpenAI error: {e}")
            return f"⚠️ Ошибка OpenAI: {str(e)}"


# Глобальный экземпляр клиента (создается при импорте)
def _create_default_openai_client() -> Optional[OpenAIClient]:
    """Создать клиент по умолчанию, если API ключ настроен"""
    try:
        if settings.openai_api_key:
            return OpenAIClient()
    except Exception:
        pass
    return None


openai_client = _create_default_openai_client()
