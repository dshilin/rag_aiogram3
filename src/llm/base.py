from abc import ABC, abstractmethod
from typing import Optional, List


# Системный промт для ИИ-агента АН
SYSTEM_PROMPT_AN = """Ты — ИИ-агент, основанный исключительно на официальной литературе сообщества Анонимных Наркоманов (АН).

Твоя задача — отвечать пользователю строго в рамках следующих источников:

1. Базовый текст АН  
2. Ежедневник «Только сегодня»  
3. «Это работает – как и почему»

СТРОГИЕ ПРАВИЛА ОТВЕТА:

1. Каждый ответ ОБЯЗАТЕЛЬНО начинается с фразы:
   «В нашей литературе на эту тему сказано:»

2. Ответ всегда содержит ПРЯМЫЕ ДОСЛОВНЫЕ ЦИТАТЫ.
   - Цитаты не перефразируются.
   - Никаких пересказов.
   - Никаких интерпретаций.
   - Никаких выводов от себя.

3. После каждой цитаты обязательно указывается источник и страница в формате:
   «Название книги, стр. XX»

4. Если по теме есть упоминания в нескольких доступных источниках — приведи цитаты из КАЖДОГО доступного источника.

5. Если прямой формулировки по вопросу нет:
   - приведи наиболее близкие по смыслу дословные цитаты,
   - не пиши, что информации нет,
   - не делай выводов,
   - не добавляй объяснений.

6. Если вопрос не касается АН или выздоровления — ответи:
   «Этот вопрос не относится к литературе АН.»

7. Если пользователь просит помощи:
   - приведи соответствующую цитату о поиске поддержки,
   - добавь фразу: «Рекомендуем посетить ближайшую группу АН в вашем регионе.»

8. Запрещено:
   - добавлять эмодзи
   - делать списки без цитат
   - писать пояснения вне цитат
   - писать от себя
   - ссылаться на несуществующие страницы
   - придумывать формулировки

Стиль: спокойный, нейтральный, официальный.
Ответ всегда состоит ТОЛЬКО из:
- вступительной фразы
- блока(ов) прямых цитат с источниками."""


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
        conversation_history: Optional[List[dict]] = None,
    ) -> str:
        """
        Отправить запрос к LLM

        Args:
            question: Вопрос пользователя
            context: Контекст из RAG (опционально)
            sources: Источники из RAG для цитирования (опционально)
            conversation_history: История диалога для поддержания контекста (опционально)

        Returns:
            Текст ответа от модели или сообщение об ошибке
        """
        pass

    def _build_prompt(
        self,
        question: str,
        context: Optional[str] = None,
        sources: Optional[List[str]] = None,
        conversation_history: Optional[List[dict]] = None,
    ) -> str:
        """
        Построить промпт с контекстом, источниками и историей диалога

        Args:
            question: Вопрос пользователя
            context: Контекст из RAG (опционально)
            sources: Источники для цитирования (опционально)
            conversation_history: История диалога (опционально)

        Returns:
            Сформированный промпт
        """
        parts = []

        # Добавляем историю диалога
        if conversation_history:
            history_text = "История диалога:\n"
            for msg in conversation_history:
                role = "Пользователь" if msg["role"] == "user" else "Ассистент"
                history_text += f"{role}: {msg['content']}\n"
            parts.append(history_text)

        # Добавляем контекст
        if context:
            parts.append(f"Контекст из литературы АН:\n{context}\n")

        # Добавляем источники
        if sources:
            parts.append(f"Источники: {', '.join(sources)}\n")

        # Добавляем вопрос
        parts.append(f"Вопрос: {question}")

        return "\n\n".join(parts) if parts else question
