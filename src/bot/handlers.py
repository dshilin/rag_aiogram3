from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

from src.rag.service import RAGService
from src.llm.factory import get_llm_client
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

# Инициализация LLM клиента на основе настроек
llm_client = get_llm_client(
    provider=settings.llm_provider,
    model=settings.llm_model if settings.llm_model else None,
    temperature=settings.llm_temperature,
    max_tokens=settings.llm_max_tokens,
)


@router.message(Command("start"))
@trace()
async def cmd_start(message: Message):
    """Обработка команды /start"""
    log_call_flow(f"Command /start from user {message.from_user.id}")
    await message.answer(
        f"👋 Привет! Я RAG-бот с {settings.llm_provider.upper()}.\n\n"
        "Задайте мне вопрос, и я найду ответ в базе знаний и сгенерирую ответ с помощью LLM.\n"
        "Используйте /help для получения дополнительной информации."
    )


@router.message(Command("help"))
@trace()
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
@trace()
async def cmd_status(message: Message):
    """Обработка команды /status"""
    log_call_flow(f"Command /status from user {message.from_user.id}")
    count = rag_service.get_document_count()
    await message.answer(
        f"📊 В базе знаний: {count} документов\n"
        f"🤖 LLM провайдер: {settings.llm_provider}"
    )


@router.message(Command("add"))
@trace()
async def cmd_add(message: Message):
    """Обработка команды /add"""
    log_call_flow(f"Command /add from user {message.from_user.id}")
    await message.answer(
        "📎 Отправьте мне текстовый файл (.txt, .md) или просто текст, "
        "который нужно добавить в базу знаний."
    )


@router.message(F.text)
@trace()
async def handle_text(message: Message):
    """Обработка текстовых сообщений - поиск через RAG + генерация ответа через LLM"""
    # Generate request ID for this conversation
    request_id = generate_request_id()
    set_request_id(request_id)

    # Log user message
    log_user_message(
        user_id=message.from_user.id,
        username=message.from_user.username,
        message_text=message.text
    )

    query = message.text
    log_call_flow(f"Processing text message from user {message.from_user.id}")

    await message.answer("🔍 Ищу ответ...")

    try:
        # Получаем контекст из RAG
        log_call_flow("Querying RAG service")
        results = rag_service.query_with_metadata(query)

        if results:
            log_call_flow(f"RAG found {len(results)} results")
            # Формируем контекст из найденных фрагментов
            context = "\n\n".join([r.content for r in results])

            # Генерируем ответ с помощью LLM
            await message.answer("🤖 Генерирую ответ...")
            log_call_flow("Calling LLM with RAG context")
            response = llm_client.ask(query, context)
        else:
            log_call_flow("RAG found no results, calling LLM without context")
            # Если контекст не найден, спрашиваем напрямую у LLM
            await message.answer("🤖 Генерирую ответ...")
            response = llm_client.ask(query)

        if response and not response.startswith("⚠️") and not response.startswith("Ошибка"):
            final_answer = f"💡 Ответ:\n\n{response}"
        else:
            final_answer = response

        log_call_flow(f"Sending response to user {message.from_user.id}")
        await message.answer(final_answer)
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        await message.answer(f"⚠️ Произошла ошибка: {str(e)}")


@router.message(F.document)
@trace()
async def handle_document(message: Message):
    """Обработка документов для добавления в базу знаний"""
    # Generate request ID for this operation
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
