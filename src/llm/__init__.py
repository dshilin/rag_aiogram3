"""LLM clients module"""

from src.llm.base import LLMClient, SYSTEM_PROMPT_AN
from src.llm.factory import LLMFactory, get_llm_client

__all__ = [
    "LLMClient",
    "SYSTEM_PROMPT_AN",
    "YandexGPTClient",
    "yandex_gpt",
    "VseGPTClient",
    "vsegpt",
    "OpenAIClient",
    "openai_client",
    "LLMFactory",
    "get_llm_client",
]


def __getattr__(name):
    if name in ("YandexGPTClient", "yandex_gpt"):
        from src.llm.yandex_gpt import YandexGPTClient, yandex_gpt
        if name == "YandexGPTClient":
            return YandexGPTClient
        return yandex_gpt
    if name in ("VseGPTClient", "vsegpt"):
        from src.llm.vsegpt import VseGPTClient, vsegpt
        if name == "VseGPTClient":
            return VseGPTClient
        return vsegpt
    if name in ("OpenAIClient", "openai_client"):
        from src.llm.openai_client import OpenAIClient, openai_client
        if name == "OpenAIClient":
            return OpenAIClient
        return openai_client
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return __all__
