import requests
from typing import Optional
from loguru import logger

from src.core.config import settings
from src.llm.base import LLMClient
from src.utils.logging import trace, log_call_flow


class VseGPTClient(LLMClient):
    """Клиент для работы с VseGPT.ru API"""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 300,
    ):
        """
        Инициализация клиента VseGPT.ru

        Args:
            model: Название модели (например, gpt-4o-mini, gpt-4, и т.д.)
            temperature: Температура генерации (0.0 - 1.0)
            max_tokens: Максимальное количество токенов в ответе
        """
        self._model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_url = "https://api.vsegpt.ru/v1/chat/completions"

    @property
    def provider_name(self) -> str:
        return "vsegpt"

    @property
    def model_name(self) -> str:
        return self._model

    @trace(show_result=False)
    def ask(self, question: str, context: Optional[str] = None) -> str:
        """
        Отправить запрос к VseGPT.ru

        Args:
            question: Вопрос пользователя
            context: Контекст из RAG (опционально)

        Returns:
            Текст ответа от модели или сообщение об ошибке
        """
        log_call_flow(f"VseGPT request: '{question[:50]}...' with context={context is not None}")
        
        if not settings.vsegpt_api_key:
            logger.warning("VseGPT API key not configured")
            return "⚠️ VseGPT.ru не настроен. Проверьте переменную окружения VSEGPT_API_KEY."

        prompt = self._build_prompt(question, context)
        log_call_flow(f"Built prompt: '{prompt[:50]}...'")

        headers = {
            "Authorization": f"Bearer {settings.vsegpt_api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self._model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "user", "content": prompt}
            ],
        }

        try:
            log_call_flow(f"VseGPT API URL: {self.api_url}")
            log_call_flow(f"VseGPT request payload: model={self._model}, temperature={self.temperature}, max_tokens={self.max_tokens}, prompt={prompt[:100]}...")
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30,
            )

            if response.ok:
                result = response.json()
                answer = result["choices"][0]["message"]["content"]
                log_call_flow(f"VseGPT response received: '{answer[:50]}...'")
                return answer
            else:
                logger.error(f"VseGPT error {response.status_code}")
                return f"Ошибка VseGPT.ru: {response.status_code}"

        except requests.exceptions.Timeout:
            logger.warning("VseGPT request timeout")
            return "⏱️ Превышено время ожидания ответа от VseGPT.ru"
        except requests.exceptions.RequestException as e:
            logger.error(f"VseGPT request error: {e}")
            return f"⚠️ Ошибка соединения с VseGPT.ru: {str(e)}"
        except KeyError as e:
            logger.error(f"VseGPT response parsing error: {e}")
            return f"⚠️ Ошибка обработки ответа VseGPT.ru: {str(e)}"


# Глобальный экземпляр клиента
vsegpt = VseGPTClient()
