from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command

from src.rag.service import RAGService

router = Router()
rag_service = RAGService()


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
    """Обработка текстовых сообщений - поиск через RAG"""
    query = message.text
    
    await message.answer("🔍 Ищу ответ...")
    
    try:
        result = rag_service.query(query)
        
        if result:
            response = f"💡 Ответ:\n\n{result}"
        else:
            response = "😕 Не нашел информацию по вашему запросу.\n\nПопробуйте переформулировать вопрос или добавьте больше документов в базу знаний."
        
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
