import sys
from functools import wraps
from typing import Callable, Any
from loguru import logger

from src.core.config import settings


def setup_logging():
    """Настроить логирование"""
    logger.remove()

    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=settings.log_level,
    )

    logger.add(
        "logs/bot.log",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        level=settings.log_level,
        rotation="10 MB",
        retention="7 days",
    )

    return logger


def trace(show_result: bool = True):
    """
    Декоратор для трассировки вызовов функций

    Args:
        show_result: Показывать результат выполнения

    Returns:
        Декоратор
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            func_name = func.__name__
            logger.debug(f"→ Вызов {func_name}")
            
            try:
                result = func(*args, **kwargs)
                
                if show_result:
                    logger.debug(f"← {func_name} вернул: {str(result)[:100]}")
                
                return result
            except Exception as e:
                logger.error(f"✗ {func_name} выбросил: {e}")
                raise
        
        return wrapper
    return decorator


def log_call_flow(message: str):
    """
    Записать сообщение о потоке выполнения

    Args:
        message: Сообщение для логирования
    """
    logger.debug(f"FLOW: {message}")
