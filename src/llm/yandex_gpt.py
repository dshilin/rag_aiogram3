import requests
from typing import Optional

from src.core.config import settings


class YandexGPTClient:
    """Клиент для работы с YandexGPT API"""

    def __init__(
        self,
        model: str = "yandexgpt-lite",
        temperature: float = 0.7,
        max_tokens: int = 300,
    ):
        """
        Инициализация клиента YandexGPT

        Args:
            model: Название модели (yandexgpt-lite или yandexgpt)
            temperature: Температура генерации (0.0 - 1.0)
            max_tokens: Максимальное количество токенов в ответе
        """
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

    def ask(self, question: str, context: Optional[str] = None) -> str:
        """
        Отправить запрос к YandexGPT

        Args:
            question: Вопрос пользователя
            context: Контекст из RAG (опционально)

        Returns:
            Текст ответа от модели или сообщение об ошибке
        """
        if not settings.yandex_folder_id or not settings.yandex_api_key:
            return "⚠️ YandexGPT не настроен. Проверьте переменные окружения YANDEX_FOLDER_ID и YANDEX_API_KEY."

        # Формируем промпт с контекстом если он есть
        if context:
            prompt = (
                f"Используй следующий контекст для ответа на вопрос:\n\n"
                f"Контекст:\n{context}\n\n"
                f"Вопрос: {question}\n\n"
                f"Ответ:"
            )
        else:
            prompt = question

        headers = {
            "Authorization": f"Bearer {settings.yandex_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "modelUri": f"gpt://{settings.yandex_folder_id}/{self.model}/latest",
            "completionOptions": {
                "stream": False,
                "temperature": self.temperature,
                "maxTokens": self.max_tokens,
            },
            "messages": [
                {"role": "user", "text": prompt}
            ],
        }

        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30,
            )

            if response.ok:
                result = response.json()
                return result["result"]["alternatives"][0]["message"]["text"]
            else:
                return f"Ошибка YandexGPT: {response.status_code}"

        except requests.exceptions.Timeout:
            return "⏱️ Превышено время ожидания ответа от YandexGPT"
        except requests.exceptions.RequestException as e:
            return f"⚠️ Ошибка соединения с YandexGPT: {str(e)}"
        except KeyError as e:
            return f"⚠️ Ошибка обработки ответа YandexGPT: {str(e)}"


# Глобальный экземпляр клиента
yandex_gpt = YandexGPTClient()
