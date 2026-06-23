import uuid
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
except (ValueError, Exception):
    llm_client = None
    USE_LLM = False


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
        user_id = abs(hash(req.session_id))
        session_manager.start_new_session(user_id)
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
        user_id = abs(hash(req.session_id))
        query = req.message

        if USE_LLM and llm_client:
            category = classify_query(llm_client, query)

            if category == QueryCategory.GREETING:
                return ChatResponse(
                    reply="👋 Привет! Я RAG-бот с литературой АН. Задайте вопрос по теме выздоровления.",
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
            results = get_rag_service().query_with_metadata(query, top_k=5, score_threshold=0.3)

            if results:
                context_parts = []
                for chunk in results:
                    citation = chunk.metadata.get("citation_label", chunk.source) if chunk.metadata else chunk.source
                    context_parts.append(
                        f"[Источник: {citation}]\n{chunk.content}"
                    )
                    sources.append({
                        "source": citation,
                        "content": chunk.content[:200],
                    })

                context = "\n\n---\n\n".join(context_parts)

                answer = llm_client.ask(
                    question=query,
                    context=context,
                    sources=[s["source"] for s in sources],
                    conversation_history=session_history,
                )

                # ponytail: if LLM refuses to answer, suppress sources
                _refusal_patterns = ("не могу", "не могу обсуждать", "не могу ответить", "не уместно", "не этично")
                if sources and not any(p in answer.lower() for p in _refusal_patterns):
                    sources_text = "\n\n📚 **Источники:**\n"
                    sources_text += "\n".join(f"• {s['source']}" for s in sources)
                    answer += sources_text

                response = answer
            else:
                response = (
                    "😕 Не нашел информацию по вашему запросу в литературе АН.\n\n"
                    "Попробуйте переформулировать вопрос или обратитесь к:\n"
                    "• Базовому тексту АН\n"
                    "• Ежедневнику «Только Сегодня»\n"
                    "• Книге «Это работает – как и почему»"
                )
        else:
            result = get_rag_service().query(query)
            if result:
                response = f"💡 Ответ:\n\n{result}"
            else:
                response = (
                    "😕 Не нашел информацию по вашему запросу.\n\n"
                    "Попробуйте переформулировать вопрос или добавьте больше документов в базу знаний."
                )

        session_manager.add_message(user_id, "user", query)
        session_manager.add_message(user_id, "assistant", response)

        return ChatResponse(reply=response, category="an_question", sources=sources if USE_LLM else None)
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        return ChatResponse(
            reply=f"⚠️ Произошла ошибка: {str(e)}",
            category="an_question",
        )
