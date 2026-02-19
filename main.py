import asyncio

from loguru import logger

from src.bot.dispatcher import dp, bot
from src.bot.handlers import router
from src.utils.logging import setup_logging


async def main():
    """Точка входа приложения"""
    # Настройка логирования
    setup_logging()
    
    # Регистрация роутеров
    dp.include_router(router)
    
    logger.info("Бот запускается...")
    
    # Удаление webhook при запуске (для polling)
    await bot.delete_webhook(drop_pending_updates=True)
    
    # Запуск polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен")
