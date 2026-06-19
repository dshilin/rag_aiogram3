from src.llm.yandex_gpt import YandexGPTClient
from src.llm.vsegpt import VseGPTClient
from src.llm.openai_client import OpenAIClient

_PROVIDERS = {
    "yandex": YandexGPTClient,
    "vsegpt": VseGPTClient,
    "openai": OpenAIClient,
}


def get_llm_client(provider: str, **kwargs):
    if provider not in _PROVIDERS:
        available = ", ".join(_PROVIDERS)
        raise ValueError(f"Неизвестный провайдер: {provider}. Доступные: {available}")
    return _PROVIDERS[provider](**kwargs)
