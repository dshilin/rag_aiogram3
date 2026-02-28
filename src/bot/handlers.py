from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

from src.rag.service import RAGService
from src.llm import get_llm_client, SYSTEM_PROMPT_AN
from src.llm.openai_client import OpenAIClient

router = Router()
rag_service = RAGService()

# Инициализация LLM клиента (используем OpenAI по умолчанию)
llm_client = None
USE_LLM = False

try:
    # Пытаемся создать OpenAI клиент (он использует SYSTEM_PROMPT_AN по умолчанию)
    llm_client = OpenAIClient(
        model="gpt-3.5-turbo",
        temperature=0.3,
        max_tokens=500,
    )
    USE_LLM = True
except (ValueError, Exception) as e:
    llm_client = None
    USE_LLM = False


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Обработка команды /start"""
    await message.answer(
        "👋 Привет! Я RAG-бот.\n\n"
        "Задайте мне вопрос, и я найду ответ в базе знаний.\n"
        "Используйте /help для получения дополнительной информации."
    )


@router.message(Command("help"))
async def cmd_help(message: Message):
    """Обработка команды /help"""
    await message.answer(
        "📚 Доступные команды:\n\n"
        "/start - Запустить бота\n"
        "/help - Показать эту справку\n"
        "/add - Добавить документ (отправьте файл после команды)\n"
        "/status - Показать статус базы знаний\n\n"
        "Просто отправьте сообщение с вопросом, и я поищу ответ."
    )


@router.message(Command("status"))
async def cmd_status(message: Message):
    """Обработка команды /status"""
    count = rag_service.get_document_count()
    await message.answer(f"📊 В базе знаний: {count} документов")


@router.message(Command("add"))
async def cmd_add(message: Message):
    """Обработка команды /add"""
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
        await message.answer(f"⚠️ Произошла ошибка: {str(e)}")


@router.message(F.document)
async def handle_document(message: Message):
    """Обработка документов для добавления в базу знаний"""
    await message.answer("📥 Загружаю документ...")
    
    try:
        file = await message.document.get_file()
        content = await file.read()
        text = content.decode("utf-8")
        
        rag_service.add_documents([text])
        
        await message.answer("✅ Документ успешно добавлен в базу знаний!")
    except Exception as e:
        await message.answer(f"⚠️ Ошибка при обработке документа: {str(e)}")
