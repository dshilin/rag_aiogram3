import requests
from typing import Optional
from loguru import logger

from src.core.config import settings
from src.llm.base import LLMClient
from src.utils.logging import trace, log_call_flow


class YandexGPTClient(LLMClient):
    """Клиент для работы с YandexGPT API через API-ключ.

    The original implementation constructed the model URI using the
    ``yandex_folder_id`` setting and the ``model`` argument passed during
    initialization.  If the user accidentally provided a full URI as the
    model name (for example by copying the `modelUri` value from a notebook
    example into ``LLM_MODEL``), the resulting string would look like
    ``gpt://<folder>/gpt://<folder>/yandexgpt/latest/latest``.  The API then
    returned ``400 invalid model_uri`` which is exactly the error reported by
    the user.

    To make the client more robust we now normalize the model identifier in
    :meth:`_build_model_uri`.  Both bare model names and complete URIs are
    accepted, and we validate that a folder ID is available before making the
    request.
    """

    def __init__(
        self,
        model: str = "yandexgpt",
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
        self._model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

    @property
    def provider_name(self) -> str:
        return "yandex"

    @property
    def model_name(self) -> str:
        return self._model

    def _build_model_uri(self) -> str:
        """Compose the ``modelUri`` field sent to Yandex.

        The field has the form ``gpt://<folder_id>/<model>/latest``.
        """
        # Use default model if not specified
        model_name = self._model if self._model else "yandexgpt"
        
        # Build URI: gpt://folder_id/model_name/latest
        return f"gpt://{settings.yandex_folder_id}/{model_name}/latest"

    @trace(show_result=False)
    def ask(self, question: str, context: Optional[str] = None) -> str:
        """
        Отправить запрос к YandexGPT

        Args:
            question: Вопрос пользователя
            context: Контекст из RAG (опционально)

        Returns:
            Текст ответа от модели или сообщение об ошибке
        """
        log_call_flow(f"YandexGPT request: '{question[:50]}...' with context={context is not None}")
        
        if not settings.yandex_folder_id or not settings.yandex_api_key:
            logger.warning("YandexGPT credentials not configured")
            return "⚠️ YandexGPT не настроен. Проверьте переменные окружения YANDEX_FOLDER_ID и YANDEX_API_KEY."

        prompt = self._build_prompt(question, context)
        log_call_flow(f"Built prompt: '{prompt[:50]}...'")

        headers = {
            "Authorization": f"Bearer {settings.yandex_api_key}",
            "Content-Type": "application/json",
        }

        # build the model URI; the user may supply either a simple model
        # name ("yandexgpt", "yandexgpt-lite" etc.) or a full URI
        # ("gpt://<folder>/<model>/latest").  If the latter is provided we
        # respect it verbatim, otherwise we glue the folder ID and the latest
        # tag.  This avoids a common misconfiguration where LLM_MODEL is set to
        # a complete URI and the client would prepend another prefix,
        # resulting in an invalid model_uri error from the API.
        model_uri = self._build_model_uri()

        payload = {
            "modelUri": model_uri,
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
            log_call_flow(f"YandexGPT API URL: {self.api_url}")
            log_call_flow(f"YandexGPT request payload: modelUri={model_uri}, temperature={self.temperature}, maxTokens={self.max_tokens}, prompt={prompt[:100]}...")
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
                timeout=30,
            )

            if response.ok:
                result = response.json()
                answer = result["result"]["alternatives"][0]["message"]["text"]
                log_call_flow(f"YandexGPT response received: '{answer[:50]}...'")
                return answer
            else:
                error_detail = response.text

                # common misconfiguration: user supplied a bad model URI or set
                # LLM_MODEL incorrectly
                if response.status_code == 400 and "invalid model_uri" in error_detail:
                    logger.warning(f"YandexGPT invalid model_uri: {error_detail}")
                    return (
                        "⚠️ YandexGPT: неверно указан идентификатор модели. "
                        "Проверьте значение LLM_MODEL и YANDEX_FOLDER_ID."
                    )

                logger.error(f"YandexGPT error {response.status_code}: {error_detail}")
                return f"Ошибка YandexGPT: {response.status_code} - {error_detail}"

        except requests.exceptions.Timeout:
            logger.warning("YandexGPT request timeout")
            return "⏱️ Превышено время ожидания ответа от YandexGPT"
        except requests.exceptions.RequestException as e:
            logger.error(f"YandexGPT request error: {e}")
            return f"⚠️ Ошибка соединения с YandexGPT: {str(e)}"
        except KeyError as e:
            logger.error(f"YandexGPT response parsing error: {e}")
            return f"⚠️ Ошибка обработки ответа YandexGPT: {str(e)}"


# Глобальный экземпляр клиента
yandex_gpt = YandexGPTClient()
