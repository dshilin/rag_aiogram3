from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from src.core.config import settings

bot = Bot(token=settings.bot_token)
dp = Dispatcher(storage=MemoryStorage())
