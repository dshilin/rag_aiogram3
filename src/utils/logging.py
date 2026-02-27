import sys
import uuid
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable, Optional

from loguru import logger

from src.core.config import settings

# Контекстная переменная для отслеживания запросов/вызовов
_request_id: ContextVar[str] = ContextVar("request_id", default="main")


def get_request_id() -> str:
    """Получить текущий request ID"""
    return _request_id.get()


def set_request_id(request_id: str) -> None:
    """Установить request ID для текущего контекста"""
    _request_id.set(request_id)


def generate_request_id() -> str:
    """Сгенерировать новый request ID"""
    return str(uuid.uuid4())[:8]


def _add_request_id(record):
    """Добавляет request_id в запись лога"""
    record["extra"]["request_id"] = get_request_id()
    return True


def _category_filter(category_name):
    """Создаёт фильтр по категории"""
    def filter_func(record):
        record["extra"]["request_id"] = get_request_id()
        return record["extra"].get("category") == category_name
    return filter_func


class CallTracer:
    """Декоратор для трассировки вызовов функций/методов"""

    def __init__(self, show_args: bool = True, show_result: bool = True):
        self.show_args = show_args
        self.show_result = show_result

    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            request_id = get_request_id()
            func_name = f"{func.__module__}.{func.__qualname__}"

            # Логирование входа
            if self.show_args:
                args_info = self._format_args(args, kwargs)
                logger.debug(f"[{request_id}] ENTER → {func_name}({args_info})")
            else:
                logger.debug(f"[{request_id}] ENTER → {func_name}()")

            try:
                result = await func(*args, **kwargs)
                if self.show_result:
                    logger.debug(f"[{request_id}] EXIT  ← {func_name} = {self._format_result(result)}")
                else:
                    logger.debug(f"[{request_id}] EXIT  ← {func_name}")
                return result
            except Exception as e:
                logger.error(f"[{request_id}] ERROR ← {func_name} raised {type(e).__name__}: {e}")
                raise

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            request_id = get_request_id()
            func_name = f"{func.__module__}.{func.__qualname__}"

            # Логирование входа
            if self.show_args:
                args_info = self._format_args(args, kwargs)
                logger.debug(f"[{request_id}] ENTER → {func_name}({args_info})")
            else:
                logger.debug(f"[{request_id}] ENTER → {func_name}()")

            try:
                result = func(*args, **kwargs)
                if self.show_result:
                    logger.debug(f"[{request_id}] EXIT  ← {func_name} = {self._format_result(result)}")
                else:
                    logger.debug(f"[{request_id}] EXIT  ← {func_name}")
                return result
            except Exception as e:
                logger.error(f"[{request_id}] ERROR ← {func_name} raised {type(e).__name__}: {e}")
                raise

        from asyncio import iscoroutinefunction
        return async_wrapper if iscoroutinefunction(func) else sync_wrapper

    @staticmethod
    def _format_args(args: tuple, kwargs: dict) -> str:
        """Форматировать аргументы функции для логирования"""
        parts = []

        # Пропускаем первый аргумент, если это self/cls
        start_idx = 0
        if args and args[0].__class__.__name__ in ("self", "cls"):
            start_idx = 1

        for arg in args[start_idx:]:
            arg_str = str(arg)
            if len(arg_str) > 50:
                arg_str = arg_str[:47] + "..."
            parts.append(arg_str)

        for key, value in kwargs.items():
            val_str = str(value)
            if len(val_str) > 50:
                val_str = val_str[:47] + "..."
            parts.append(f"{key}={val_str}")

        return ", ".join(parts)

    @staticmethod
    def _format_result(result: Any) -> str:
        """Форматировать результат функции для логирования"""
        if result is None:
            return "None"
        result_str = str(result)
        if len(result_str) > 100:
            result_str = result_str[:97] + "..."
        return result_str


def setup_logging():
    """Настроить логирование"""
    logger.remove()

    # Консольный вывод
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <magenta>{extra[request_id]}</magenta> - <level>{message}</level>",
        level=settings.log_level,
        filter=_add_request_id,
    )

    # Основной лог файл
    logger.add(
        "logs/app_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {extra[request_id]} | {message}",
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        filter=_add_request_id,
    )

    # Лог ошибок
    logger.add(
        "logs/errors_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {extra[request_id]} | {message}",
        level="ERROR",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        filter=_add_request_id,
    )

    # Лог сообщений пользователей
    logger.add(
        "logs/user_messages_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {message}",
        level="INFO",
        rotation="10 MB",
        retention="30 days",
        filter=_category_filter("user_message"),
    )

    # Лог потока вызовов
    logger.add(
        "logs/call_flow_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {message}",
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        filter=_category_filter("call_flow"),
    )

    return logger


def log_user_message(user_id: int, username: Optional[str], message_text: str) -> None:
    """Логировать сообщение пользователя"""
    logger.info(
        f"USER [{user_id}] @{username or 'no_username'}: {message_text}",
        category="user_message"
    )


def log_call_flow(message: str) -> None:
    """Логировать информацию о потоке вызовов"""
    logger.debug(message, category="call_flow")


# Экспортируем декоратор
trace = CallTracer
