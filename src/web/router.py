import asyncio
from pathlib import Path
from typing import Optional
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from loguru import logger

from src.llm import get_llm_client
from src.core.config import settings
from src.bot.session import session_manager
from src.bot.classifier import classify_query, QueryCategory

router = APIRouter()

_rag_service = None

def get_rag_service():
    global _rag_service
    if _rag_service is None:
        from src.rag.service import RAGService
        _rag_service = RAGService()
    return _rag_service

llm_client = None
USE_LLM = False
try:
    llm_client = get_llm_client(
        provider=settings.llm_provider,
        model=settings.llm_model or None,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
    USE_LLM = True
except Exception as e:
    logger.warning(f"LLM клиент не инициализирован ({e}) — веб-чат работает в режиме поиска без генерации")
    llm_client = None
    USE_LLM = False


def _session_key(session_id: str) -> str:
    # неймспейс "web:" исключает пересечение с Telegram user_id в общем SessionManager
    return f"web:{session_id}"


class ChatRequest(BaseModel):
    message: str
    session_id: str


class ChatResponse(BaseModel):
    reply: str
    category: str
    sources: Optional[list[dict]] = None


class NewSessionRequest(BaseModel):
    session_id: str


class NewSessionResponse(BaseModel):
    success: bool


@router.post("/api/session/new", response_model=NewSessionResponse)
async def new_session(req: NewSessionRequest):
    try:
        session_manager.start_new_session(_session_key(req.session_id))
        return NewSessionResponse(success=True)
    except Exception as e:
        logger.error(f"Error starting new session: {e}")
        return NewSessionResponse(success=False)


@router.get("/")
async def index():
    html = (Path(__file__).parent / "templates" / "chat.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@router.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        user_id = _session_key(req.session_id)
        query = req.message

        if USE_LLM and llm_client:
            # to_thread: внутри синхронный requests — не блокируем event loop
            category = await asyncio.to_thread(classify_query, llm_client, query)

            if category == QueryCategory.GREETING:
                return ChatResponse(
                    reply="👋 Привет! Задайте вопрос по теме выздоровления.",
                    category="greeting",
                )

            elif category == QueryCategory.HELP_REQUEST:
                return ChatResponse(
                    reply=(
                        "В нашей литературе на эту тему сказано:\n\n"
                        "«Анонимные Наркоманы — это сообщество мужчин и женщин, которые делятся своим опытом, "
                        "силой и надеждой, чтобы помочь друг другу выздороветь от наркомании.»\n\n"
                        "Базовый текст АН, стр. XXI\n\n"
                        "Рекомендуем посетить ближайшую группу АН в вашем регионе."
                    ),
                    category="help_request",
                )

            elif category == QueryCategory.OFF_TOPIC:
                return ChatResponse(
                    reply="Этот вопрос не относится к литературе АН.",
                    category="off_topic",
                )

        session_history = session_manager.get_history(user_id, limit=10)

        sources = []

        if USE_LLM and llm_client:
            results = await asyncio.to_thread(
                lambda: get_rag_service().query_with_metadata(query, top_k=5)
            )

            if results:
                context_parts = []
                for chunk in results:
                    citation = chunk.citation_label
                    context_parts.append(
                        f"[Источник: {citation}]\n{chunk.content}"
                    )
                    sources.append({
                        "source": citation,
                        "content": chunk.content[:200],
                    })

                context = "\n\n---\n\n".join(context_parts)

                answer = await asyncio.to_thread(
                    lambda: llm_client.ask(
                        question=query,
                        context=context,
                        sources=[s["source"] for s in sources],
                        conversation_history=session_history,
                    )
                )

                response = answer

                # Сохраняем в сессию только успешные ответы —
                # отказы и «не нашёл» не должны попадать в контекст диалога
                session_manager.add_message(user_id, "user", query)
                session_manager.add_message(user_id, "assistant", response)
            else:
                response = (
                    "😕 Не нашел информацию по вашему запросу в литературе АН.\n\n"
                    "Попробуйте переформулировать вопрос или обратитесь к:\n"
                    "• Базовому тексту АН\n"
                    "• Ежедневнику «Только Сегодня»\n"
                    "• Книге «Это работает – как и почему»"
                )
        else:
            result = await asyncio.to_thread(lambda: get_rag_service().query(query))
            if result:
                response = f"💡 Ответ:\n\n{result}"
            else:
                response = (
                    "😕 Не нашел информацию по вашему запросу.\n\n"
                    "Попробуйте переформулировать вопрос или добавьте больше документов в базу знаний."
                )

        return ChatResponse(reply=response, category="an_question", sources=sources if USE_LLM else None)
    except Exception:
        logger.exception("Error processing message")
        return ChatResponse(
            reply="⚠️ Произошла внутренняя ошибка. Попробуйте ещё раз позже.",
            category="an_question",
        )
