import sys
import uuid
import inspect
from functools import wraps
from contextvars import ContextVar

from loguru import logger

_request_id: ContextVar[str] = ContextVar("request_id", default="main")


def get_request_id() -> str:
    return _request_id.get()


def set_request_id(request_id: str) -> None:
    _request_id.set(request_id)


def generate_request_id() -> str:
    return str(uuid.uuid4())[:8]


def _add_request_id(record):
    record["extra"]["request_id"] = get_request_id()
    return True


def trace(func):
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        request_id = get_request_id()
        name = f"{func.__module__}.{func.__qualname__}"
        logger.debug(f"[{request_id}] ENTER {name}")
        try:
            result = await func(*args, **kwargs)
            logger.debug(f"[{request_id}] EXIT {name}")
            return result
        except Exception as e:
            logger.error(f"[{request_id}] ERROR {name}: {e}")
            raise

    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        request_id = get_request_id()
        name = f"{func.__module__}.{func.__qualname__}"
        logger.debug(f"[{request_id}] ENTER {name}")
        try:
            result = func(*args, **kwargs)
            logger.debug(f"[{request_id}] EXIT {name}")
            return result
        except Exception as e:
            logger.error(f"[{request_id}] ERROR {name}: {e}")
            raise

    return async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper


def setup_logging():
    # импорт внутри функции — чтобы модуль логирования не зависел от конфига при импорте
    from src.core.config import settings

    logger.remove()
    logger.add(sys.stdout, format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <magenta>{extra[request_id]}</magenta> - <level>{message}</level>", level=settings.log_level.upper(), filter=_add_request_id)
    logger.add("logs/errors_{time:YYYY-MM-DD}.log", format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {extra[request_id]} | {message}", level="ERROR", rotation="10 MB", retention="30 days", compression="zip", filter=_add_request_id)
    return logger


def log_user_message(user_id: int, username: str | None, message_text: str) -> None:
    logger.info(f"USER [{user_id}] @{username or 'no_username'}: {message_text}")


def log_call_flow(message: str) -> None:
    logger.debug(message)
