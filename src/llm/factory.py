from typing import Optional, Type

from src.llm.base import LLMClient


class LLMFactory:
    """Фабрика для создания LLM клиентов"""

    _providers = None

    @classmethod
    def _get_providers(cls):
        if cls._providers is None:
            from src.llm.yandex_gpt import YandexGPTClient
            from src.llm.vsegpt import VseGPTClient
            from src.llm.openai_client import OpenAIClient
            cls._providers = {
                "yandex": YandexGPTClient,
                "vsegpt": VseGPTClient,
                "openai": OpenAIClient,
            }
        return cls._providers

    @classmethod
    def register_provider(cls, name: str, client_class: Type[LLMClient]):
        """
        Зарегистрировать нового провайдера

        Args:
            name: Название провайдера
            client_class: Класс клиента
        """
        cls._get_providers()[name] = client_class

    @classmethod
    def get_client(
        cls,
        provider: str,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 500,
        system_prompt: Optional[str] = None,
    ) -> LLMClient:
        """
        Получить клиент для указанного провайдера

        Args:
            provider: Название провайдера ('yandex', 'vsegpt', 'openai', etc.)
            model: Название модели (опционально)
            temperature: Температура генерации
            max_tokens: Максимальное количество токенов
            system_prompt: Системный промт (по умолчанию используется промт АН)

        Returns:
            Экземпляр LLM клиента

        Raises:
            ValueError: Если провайдер не найден
        """
        providers = cls._get_providers()
        if provider not in providers:
            available = ", ".join(providers.keys())
            raise ValueError(
                f"Неизвестный провайдер: {provider}. Доступные: {available}"
            )

        client_class = providers[provider]

        # Создаем клиент с параметрами
        kwargs = {
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if model:
            kwargs["model"] = model
        if system_prompt:
            kwargs["system_prompt"] = system_prompt

        return client_class(**kwargs)

    @classmethod
    def list_providers(cls) -> list[str]:
        """Вернуть список зарегистрированных провайдеров"""
        return list(cls._get_providers().keys())


# Глобальная функция для получения LLM клиента
def get_llm_client(
    provider: str,
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 500,
    system_prompt: Optional[str] = None,
) -> LLMClient:
    """
    Получить LLM клиент для указанного провайдера

    Args:
        provider: Название провайдера ('yandex', 'vsegpt', 'openai', etc.)
        model: Название модели (опционально)
        temperature: Температура генерации
        max_tokens: Максимальное количество токенов
        system_prompt: Системный промт (по умолчанию используется промт АН)

    Returns:
        Экземпляр LLM клиента
    """
    return LLMFactory.get_client(
        provider,
        model,
        temperature,
        max_tokens,
        system_prompt,
    )
