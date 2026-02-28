from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

from src.rag.service import RAGService
from src.llm import get_llm_client, SYSTEM_PROMPT_AN
from src.core.config import settings
from src.utils.logging import (
    log_user_message,
    log_call_flow,
    trace,
    set_request_id,
    generate_request_id,
)
from loguru import logger

router = Router()
rag_service = RAGService()

# Инициализация LLM клиента на основе настроек из .env
llm_client = None
USE_LLM = False

try:
    # Получаем провайдера и модель из настроек
    provider = settings.llm_provider
    model = settings.llm_model if settings.llm_model else None
    temperature = settings.llm_temperature
    max_tokens = settings.llm_max_tokens
    
    # Создаем клиент через фабрику
    llm_client = get_llm_client(
        provider=provider,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    USE_LLM = True
except (ValueError, Exception) as e:
    llm_client = None
    USE_LLM = False


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Обработка команды /start"""
    log_call_flow(f"Command /start from user {message.from_user.id}")
    await message.answer(
        f"👋 Привет! Я RAG-бот с {settings.llm_provider.upper()}.\n\n"
        "Задайте мне вопрос, и я найду ответ в базе знаний и сгенерирую ответ с помощью LLM.\n"
        "Используйте /help для получения дополнительной информации."
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработка команды /help"""
    log_call_flow(f"Command /help from user {message.from_user.id}")
    await message.answer(
        "📚 Доступные команды:\n\n"
        "/start - Запустить бота\n"
        "/help - Показать эту справку\n"
        "/add - Добавить документ (отправьте файл после команды)\n"
        "/status - Показать статус базы знаний\n\n"
        "Просто отправьте сообщение с вопросом, и я поищу ответ в базе знаний."
    )


@router.message(Command("status"))
async def cmd_status(message: Message):
    """Обработка команды /status"""
    log_call_flow(f"Command /status from user {message.from_user.id}")
    count = rag_service.get_document_count()
    await message.answer(
        f"📊 В базе знаний: {count} документов\n"
        f"🤖 LLM провайдер: {settings.llm_provider}"
    )


@router.message(Command("add"))
async def cmd_add(message: Message):
    """Обработка команды /add"""
    log_call_flow(f"Command /add from user {message.from_user.id}")
    await message.answer(
        "📎 Отправьте мне текстовый файл (.txt, .md) или просто текст, "
        "который нужно добавить в базу знаний."
    )


@router.message(F.text)
async def handle_text(message: Message):
    """Обработка текстовых сообщений - поиск через RAG + LLM"""
    query = message.text

    await message.answer("🔍 Ищу ответ в литературе АН...")

    try:
        if USE_LLM and llm_client:
            # Поиск релевантных чанков в RAG
            results = rag_service.query_with_metadata(query, top_k=5, score_threshold=0.3)

            if results:
                # Формируем контекст из найденных чанков
                context_parts = []
                sources = []

                for chunk in results:
                    context_parts.append(
                        f"[Источник: {chunk.source}, стр. {chunk.page}]\n{chunk.content}"
                    )
                    sources.append(f"{chunk.source} (стр. {chunk.page})")

                context = "\n\n---\n\n".join(context_parts)

                # Запрос к LLM с системным промтом АН
                answer = llm_client.ask(
                    question=query,
                    context=context,
                    sources=sources,
                )

                # Добавляем источники
                if sources:
                    sources_text = "\n\n📚 **Источники:**\n"
                    sources_text += "\n".join(f"• {src}" for src in sources)
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
            # Режим без LLM (только RAG поиск)
            result = rag_service.query(query)

            if result:
                response = f"💡 Ответ:\n\n{result}"
            else:
                response = (
                    "😕 Не нашел информацию по вашему запросу.\n\n"
                    "Попробуйте переформулировать вопрос или добавьте больше документов в базу знаний."
                )

        await message.answer(response)
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        await message.answer(f"⚠️ Произошла ошибка: {str(e)}")


@router.message(F.document)
async def handle_document(message: Message):
    """Обработка документов для добавления в базу знаний"""
    # Генерируем request ID для этой операции
    request_id = generate_request_id()
    set_request_id(request_id)

    log_call_flow(f"Document received from user {message.from_user.id}: {message.document.file_name}")

    await message.answer("📥 Загружаю документ...")

    try:
        file = await message.document.get_file()
        content = await file.read()
        text = content.decode("utf-8")

        log_call_flow(f"Document loaded, size: {len(text)} chars")
        rag_service.add_documents([text])

        log_call_flow(f"Document added to RAG by user {message.from_user.id}")
        await message.answer("✅ Документ успешно добавлен в базу знаний!")
    except Exception as e:
        logger.error(f"Error processing document: {e}")
        await message.answer(f"⚠️ Ошибка при обработке документа: {str(e)}")
