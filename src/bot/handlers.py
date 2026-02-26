from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

from src.rag.service import RAGService
from src.llm.yandex_gpt import yandex_gpt

router = Router()
rag_service = RAGService()


@router.message(Command("start"))
async def cmd_start(message: Message):
    """Обработка команды /start"""
    await message.answer(
        "👋 Привет! Я RAG-бот с YandexGPT.\n\n"
        "Задайте мне вопрос, и я найду ответ в базе знаний и сгенерирую ответ с помощью YandexGPT.\n"
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
        "Просто отправьте сообщение с вопросом, и я поищу ответ в базе знаний."
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
    """Обработка текстовых сообщений - поиск через RAG + генерация ответа через YandexGPT"""
    query = message.text

    await message.answer("🔍 Ищу ответ...")

    try:
        # Получаем контекст из RAG
        results = rag_service.query_with_metadata(query)

        if results:
            # Формируем контекст из найденных фрагментов
            context = "\n\n".join([r.content for r in results])
            
            # Генерируем ответ с помощью YandexGPT
            await message.answer("🤖 YandexGPT генерирует ответ...")
            response = yandex_gpt.ask(query, context)
        else:
            # Если контекст не найден, спрашиваем напрямую у YandexGPT
            await message.answer("🤖 YandexGPT отвечает...")
            response = yandex_gpt.ask(query)

        if response and not response.startswith("⚠️") and not response.startswith("Ошибка"):
            final_answer = f"💡 Ответ:\n\n{response}"
        else:
            final_answer = response

        await message.answer(final_answer)
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
