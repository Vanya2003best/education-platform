"""
Middleware для логирования HTTP запросов и ответов
"""
import time
import uuid
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.utils.logger import get_logger, log_request

logger = get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware для логирования всех HTTP запросов

    Логирует:
    - Метод и путь запроса
    - Статус код ответа
    - Время обработки
    - IP адрес клиента
    - User Agent
    - Ошибки
    """

    def __init__(
            self,
            app: ASGIApp,
            log_request_body: bool = False,
            log_response_body: bool = False
    ):
        super().__init__(app)
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body

    async def dispatch(
            self, request: Request, call_next: Callable
    ) -> Response:
        # Генерируем уникальный ID для запроса
        request_id = str(uuid.uuid4())

        # Сохраняем в request state для доступа в других частях приложения
        request.state.request_id = request_id

        # Получаем информацию о клиенте
        client_host = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")

        # Начинаем отсчет времени
        start_time = time.time()

        # Логируем начало запроса
        logger.info(
            f"→ {request.method} {request.url.path}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query_params": dict(request.query_params),
                "client_host": client_host,
                "user_agent": user_agent
            }
        )

        # Опционально логируем тело запроса
        if self.log_request_body and request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
                if body:
                    logger.debug(
                        f"Request body: {body.decode()[:500]}",
                        extra={"request_id": request_id}
                    )
            except:
                pass

        # Обрабатываем запрос
        try:
            response = await call_next(request)

            # Вычисляем время обработки
            process_time = (time.time() - start_time) * 1000

            # Добавляем заголовки
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = f"{process_time:.2f}ms"

            # Определяем уровень логирования на основе статуса
            if response.status_code >= 500:
                log_level = logger.error
            elif response.status_code >= 400:
                log_level = logger.warning
            else:
                log_level = logger.info

            # Логируем ответ
            user_id = getattr(request.state, "user", None)
            user_id = user_id.id if user_id else None

            log_level(
                f"← {request.method} {request.url.path} → {response.status_code} ({process_time:.2f}ms)",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration": process_time,
                    "user_id": user_id,
                    "client_host": client_host
                }
            )

            # Также используем структурированное логирование
            log_request(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=process_time,
                user_id=user_id,
                request_id=request_id
            )

            return response

        except Exception as e:
            # Логируем ошибки
            process_time = (time.time() - start_time) * 1000

            logger.error(
                f"✗ {request.method} {request.url.path} → ERROR ({process_time:.2f}ms)",
                exc_info=True,
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration": process_time,
                    "error": str(e),
                    "client_host": client_host
                }
            )

            # Пробрасываем исключение дальше
            raise


class RequestContextMiddleware(BaseHTTPMiddleware):
    """
    Middleware для добавления контекста к запросу

    Добавляет:
    - Уникальный ID запроса
    - Timestamp начала обработки
    - Метаданные о клиенте
    """

    async def dispatch(
            self, request: Request, call_next: Callable
    ) -> Response:
        # Добавляем контекстную информацию
        request.state.start_time = time.time()

        if not hasattr(request.state, "request_id"):
            request.state.request_id = str(uuid.uuid4())

        # Извлекаем IP из заголовков (для проксированных запросов)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Берем первый IP (клиентский)
            request.state.client_ip = forwarded_for.split(",")[0].strip()
        else:
            request.state.client_ip = request.client.host if request.client else "unknown"

        # Обрабатываем запрос
        response = await call_next(request)

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware для добавления заголовков безопасности
    """

    async def dispatch(
            self, request: Request, call_next: Callable
    ) -> Response:
        response = await call_next(request)

        # Добавляем заголовки безопасности
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # Только для production
        from app.config import settings
        if settings.is_production:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.tailwindcss.com https://unpkg.com https://cdnjs.cloudflare.com; "
                "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
                "img-src 'self' data: https:; "
                "font-src 'self' data: https://cdnjs.cloudflare.com;"
            )

        return response


# Экспортируем middleware
__all__ = [
    'LoggingMiddleware',
    'RequestContextMiddleware',
    'SecurityHeadersMiddleware'
]