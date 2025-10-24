"""
Настройка структурированного логирования
"""
import logging
import sys
import json
from datetime import datetime
from typing import Any, Dict
from pathlib import Path
import traceback

from app.config import settings


class JSONFormatter(logging.Formatter):
    """JSON форматтер для структурированного логирования"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }

        # Добавляем extra поля
        if hasattr(record, "user_id"):
            log_data["user_id"] = record.user_id

        if hasattr(record, "request_id"):
            log_data["request_id"] = record.request_id

        if hasattr(record, "duration"):
            log_data["duration_ms"] = record.duration

        # Добавляем exception информацию
        if record.exc_info:
            log_data["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info)
            }

        # Добавляем дополнительные данные
        if hasattr(record, "extra_data"):
            log_data["data"] = record.extra_data

        return json.dumps(log_data, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """Человекочитаемый форматтер для разработки"""

    # Цвета для консоли
    COLORS = {
        'DEBUG': '\033[36m',  # Cyan
        'INFO': '\033[32m',  # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',  # Red
        'CRITICAL': '\033[35m',  # Magenta
        'RESET': '\033[0m'
    }

    def format(self, record: logging.LogRecord) -> str:
        # Цвет для уровня
        color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        reset = self.COLORS['RESET']

        # Базовое сообщение
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        message = f"{color}[{record.levelname}]{reset} {timestamp} - {record.name} - {record.getMessage()}"

        # Добавляем контекст
        context_parts = []

        if hasattr(record, "user_id"):
            context_parts.append(f"user_id={record.user_id}")

        if hasattr(record, "request_id"):
            context_parts.append(f"request_id={record.request_id}")

        if hasattr(record, "duration"):
            context_parts.append(f"duration={record.duration}ms")

        if context_parts:
            message += f" [{', '.join(context_parts)}]"

        # Добавляем exception
        if record.exc_info:
            message += "\n" + "".join(traceback.format_exception(*record.exc_info))

        return message


def setup_logging() -> logging.Logger:
    """
    Настроить логирование для приложения

    Returns:
        Корневой логгер
    """

    # Создаем директорию для логов
    if settings.LOG_FILE:
        log_dir = Path(settings.LOG_FILE).parent
        log_dir.mkdir(parents=True, exist_ok=True)

    # Получаем корневой логгер
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, settings.LOG_LEVEL.upper()))

    # Очищаем существующие handlers
    logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)

    # Выбираем форматтер
    if settings.LOG_FORMAT == "json":
        console_formatter = JSONFormatter()
    else:
        console_formatter = TextFormatter()

    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler (если настроен)
    if settings.LOG_FILE:
        file_handler = logging.FileHandler(settings.LOG_FILE)
        file_handler.setLevel(logging.INFO)

        # Для файла всегда используем JSON
        file_formatter = JSONFormatter()
        file_handler.setFormatter(file_formatter)

        logger.addHandler(file_handler)

    # Error file handler
    if settings.LOG_FILE:
        error_file = str(Path(settings.LOG_FILE).with_suffix('.error.log'))
        error_handler = logging.FileHandler(error_file)
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(JSONFormatter())
        logger.addHandler(error_handler)

    # Настраиваем уровни для сторонних библиотек
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.INFO)

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Получить логгер для модуля

    Args:
        name: Имя модуля

    Returns:
        Настроенный логгер
    """
    return logging.getLogger(name)


class LoggerAdapter(logging.LoggerAdapter):
    """Адаптер для добавления контекстной информации в логи"""

    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        # Добавляем extra данные в каждое сообщение
        extra = kwargs.get("extra", {})

        # Добавляем контекстные данные
        if self.extra:
            extra.update(self.extra)

        kwargs["extra"] = extra

        return msg, kwargs


def get_context_logger(name: str, **context) -> LoggerAdapter:
    """
    Получить логгер с контекстом

    Args:
        name: Имя модуля
        **context: Контекстные данные (user_id, request_id и т.д.)

    Returns:
        Логгер с контекстом

    Example:
        logger = get_context_logger(__name__, user_id=123, request_id="abc")
        logger.info("User action", extra_data={"action": "login"})
    """
    base_logger = get_logger(name)
    return LoggerAdapter(base_logger, context)


# Вспомогательные функции для специфичного логирования

def log_request(
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        user_id: int = None,
        request_id: str = None
):
    """Логировать HTTP запрос"""
    logger = get_logger("app.requests")

    extra = {
        "user_id": user_id,
        "request_id": request_id,
        "duration": duration_ms
    }

    logger.info(
        f"{method} {path} -> {status_code} ({duration_ms:.2f}ms)",
        extra=extra
    )


def log_error(
        error: Exception,
        context: Dict[str, Any] = None,
        logger_name: str = "app.errors"
):
    """Логировать ошибку с контекстом"""
    logger = get_logger(logger_name)

    extra = {"extra_data": context} if context else {}

    logger.error(
        f"Error occurred: {str(error)}",
        exc_info=True,
        extra=extra
    )


def log_security_event(
        event_type: str,
        user_id: int = None,
        ip_address: str = None,
        details: Dict[str, Any] = None
):
    """Логировать события безопасности"""
    logger = get_logger("app.security")

    extra = {
        "user_id": user_id,
        "ip_address": ip_address,
        "extra_data": details or {}
    }

    logger.warning(
        f"Security event: {event_type}",
        extra=extra
    )


def log_performance(
        operation: str,
        duration_ms: float,
        metadata: Dict[str, Any] = None
):
    """Логировать производительность"""
    logger = get_logger("app.performance")

    extra = {
        "duration": duration_ms,
        "extra_data": metadata or {}
    }

    # Предупреждение для медленных операций
    level = logging.WARNING if duration_ms > 1000 else logging.INFO

    logger.log(
        level,
        f"Operation '{operation}' took {duration_ms:.2f}ms",
        extra=extra
    )


def log_ai_check(
        submission_id: int,
        task_id: int,
        processing_time: float,
        score: float,
        status: str
):
    """Логировать AI проверку"""
    logger = get_logger("app.ai")

    extra = {
        "duration": processing_time,
        "extra_data": {
            "submission_id": submission_id,
            "task_id": task_id,
            "score": score,
            "status": status
        }
    }

    logger.info(
        f"AI check completed for submission {submission_id}: {score}/100 ({status})",
        extra=extra
    )


def log_transaction(
        user_id: int,
        transaction_type: str,
        amount: int,
        balance: int
):
    """Логировать транзакцию"""
    logger = get_logger("app.economy")

    extra = {
        "user_id": user_id,
        "extra_data": {
            "type": transaction_type,
            "amount": amount,
            "new_balance": balance
        }
    }

    logger.info(
        f"Transaction: {transaction_type} {amount:+d} coins -> balance: {balance}",
        extra=extra
    )


# Декоратор для автоматического логирования функций

def log_function_call(logger_name: str = None):
    """
    Декоратор для логирования вызовов функций

    Usage:
        @log_function_call("app.tasks")
        async def process_task(task_id: int):
            ...
    """
    import functools
    import time

    def decorator(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger = get_logger(logger_name or func.__module__)

            start_time = time.time()

            try:
                result = await func(*args, **kwargs)
                duration = (time.time() - start_time) * 1000

                logger.debug(
                    f"Function {func.__name__} completed",
                    extra={"duration": duration}
                )

                return result

            except Exception as e:
                duration = (time.time() - start_time) * 1000

                logger.error(
                    f"Function {func.__name__} failed after {duration:.2f}ms",
                    exc_info=True,
                    extra={"duration": duration}
                )

                raise

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger = get_logger(logger_name or func.__module__)

            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                duration = (time.time() - start_time) * 1000

                logger.debug(
                    f"Function {func.__name__} completed",
                    extra={"duration": duration}
                )

                return result

            except Exception as e:
                duration = (time.time() - start_time) * 1000

                logger.error(
                    f"Function {func.__name__} failed after {duration:.2f}ms",
                    exc_info=True,
                    extra={"duration": duration}
                )

                raise

        # Определяем, асинхронная ли функция
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


import asyncio

# Экспортируем основные функции
__all__ = [
    'setup_logging',
    'get_logger',
    'get_context_logger',
    'log_request',
    'log_error',
    'log_security_event',
    'log_performance',
    'log_ai_check',
    'log_transaction',
    'log_function_call',
    'JSONFormatter',
    'TextFormatter',
    'LoggerAdapter'
]