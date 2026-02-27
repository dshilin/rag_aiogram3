import sys
import uuid
from contextvars import ContextVar
from functools import wraps
from typing import Any, Callable, Optional

from loguru import logger

from src.core.config import settings

# Context variable for request/call tracking
_request_id: ContextVar[str] = ContextVar("request_id", default="main")


def get_request_id() -> str:
    """Get current request ID"""
    return _request_id.get()


def set_request_id(request_id: str) -> None:
    """Set request ID for current context"""
    _request_id.set(request_id)


def generate_request_id() -> str:
    """Generate new request ID"""
    return str(uuid.uuid4())[:8]


class CallTracer:
    """Decorator for tracing function/method calls"""

    def __init__(self, show_args: bool = True, show_result: bool = True):
        self.show_args = show_args
        self.show_result = show_result

    def __call__(self, func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            request_id = get_request_id()
            func_name = f"{func.__module__}.{func.__qualname__}"

            # Log entry
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

            # Log entry
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
        """Format function arguments for logging"""
        parts = []

        # Skip first arg if it's self/cls
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
        """Format function result for logging"""
        if result is None:
            return "None"
        result_str = str(result)
        if len(result_str) > 100:
            result_str = result_str[:97] + "..."
        return result_str


def _request_id_filter(record):
    """Filter to add request_id to record if not present"""
    record["extra"].setdefault("request_id", get_request_id())
    return True


def setup_logging():
    """Настроить логирование"""
    logger.remove()
    
    # Add handler with filter that injects request_id
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <magenta>{extra[request_id]}</magenta> - <level>{message}</level>",
        level=settings.log_level,
        filter=_request_id_filter,
    )

    logger.add(
        "logs/app_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {extra[request_id]} | {message}",
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        compression="zip",
        filter=_request_id_filter,
    )

    logger.add(
        "logs/errors_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} | {extra[request_id]} | {message}",
        level="ERROR",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        filter=_request_id_filter,
    )

    logger.add(
        "logs/user_messages_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {message}",
        level="INFO",
        rotation="10 MB",
        retention="30 days",
        filter=lambda record: record["extra"].get("category") == "user_message",
    )

    logger.add(
        "logs/call_flow_{time:YYYY-MM-DD}.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {message}",
        level="DEBUG",
        rotation="10 MB",
        retention="7 days",
        filter=lambda record: record["extra"].get("category") == "call_flow",
    )

    return logger


def log_user_message(user_id: int, username: Optional[str], message_text: str) -> None:
    """Log user message"""
    logger.info(
        f"USER [{user_id}] @{username or 'no_username'}: {message_text}",
        extra={"category": "user_message"}
    )


def log_call_flow(message: str) -> None:
    """Log call flow information"""
    logger.debug(message, extra={"category": "call_flow"})


# Export decorator
trace = CallTracer
