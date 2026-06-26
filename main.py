import asyncio
from pathlib import Path

from loguru import logger
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src.bot.dispatcher import dp, bot
from src.bot.handlers import router
from src.utils.logging import setup_logging, set_request_id, generate_request_id
from src.web.router import router as web_router

# FastAPI app
app = FastAPI(title="RAG Chat")
app.include_router(web_router)

STATIC_DIR = Path(__file__).parent / "src" / "web" / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


async def main():
    set_request_id(generate_request_id())
    setup_logging()

    # Предзагрузка RAG (эмбеддинги + FAISS индекс)
    try:
        from src.web.router import get_rag_service
        rag = get_rag_service()
        count = rag.get_document_count()
        logger.info(f"✅ RAG загружен: {count} чанков")
    except Exception as e:
        logger.warning(f"⚠️ RAG предзагрузка не удалась: {e}")

    # FastAPI web server
    config = uvicorn.Config(app, host="0.0.0.0", port=8080, log_level="info")
    server = uvicorn.Server(config)

    # Telegram bot
    dp.include_router(router)
    logger.info("Бот запускается...")
    try:
        await asyncio.wait_for(
            bot.delete_webhook(drop_pending_updates=True),
            timeout=10,
        )
        await asyncio.gather(
            dp.start_polling(bot),
            server.serve(),
        )
    except asyncio.TimeoutError:
        logger.warning("Telegram API недоступен, запущен только веб-сервер на порту 8080")
        await server.serve()
    except Exception as e:
        logger.warning(f"Ошибка подключения к Telegram: {e}. Запущен только веб-сервер.")
        await server.serve()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")
