from typing import Optional, Dict, Type

from src.llm.base import LLMClient
from src.llm.yandex_gpt import YandexGPTClient
from src.llm.vsegpt import VseGPTClient


class LLMFactory:
    """Фабрика для создания LLM клиентов"""

    _providers: Dict[str, Type[LLMClient]] = {
        "yandex": YandexGPTClient,
        "vsegpt": VseGPTClient,
    }

    @classmethod
    def register_provider(cls, name: str, client_class: Type[LLMClient]):
        """
        Зарегистрировать нового провайдера

        Args:
            name: Название провайдера
            client_class: Класс клиента
        """
        cls._providers[name] = client_class

    @classmethod
    def get_client(
        cls,
        provider: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 300,
    ) -> LLMClient:
        """
        Получить клиент для указанного провайдера

        Args:
            provider: Название провайдера ('yandex', 'vsegpt', etc.)
            model: Название модели (опционально)
            temperature: Температура генерации
            max_tokens: Максимальное количество токенов

        Returns:
            Экземпляр LLM клиента

        Raises:
            ValueError: Если провайдер не найден
        """
        if provider not in cls._providers:
            available = ", ".join(cls._providers.keys())
            raise ValueError(
                f"Неизвестный провайдер: {provider}. Доступные: {available}"
            )

        client_class = cls._providers[provider]

        # Создаем клиент с параметрами
        if model:
            return client_class(model=model, temperature=temperature, max_tokens=max_tokens)
        return client_class(temperature=temperature, max_tokens=max_tokens)

    @classmethod
    def list_providers(cls) -> list[str]:
        """Вернуть список зарегистрированных провайдеров"""
        return list(cls._providers.keys())


# Глобальная функция для получения LLM клиента
def get_llm_client(
    provider: str,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 300,
) -> LLMClient:
    """
    Получить LLM клиент для указанного провайдера

    Args:
        provider: Название провайдера ('yandex', 'vsegpt', etc.)
        model: Название модели (опционально)
        temperature: Температура генерации
        max_tokens: Максимальное количество токенов

    Returns:
        Экземпляр LLM клиента
    """
    return LLMFactory.get_client(provider, model, temperature, max_tokens)
