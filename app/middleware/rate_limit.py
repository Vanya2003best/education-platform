"""
Middleware для rate limiting (ограничение запросов)
"""
import time
from typing import Callable, Optional
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from collections import defaultdict
from datetime import datetime, timedelta

from app.utils.cache import cache_manager
from app.utils.logger import get_logger, log_security_event
from app.config import settings

logger = get_logger(__name__)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware для ограничения количества запросов

    Использует Redis для distributed rate limiting, если доступен.
    Иначе использует in-memory хранилище (только для single-instance)
    """

    def __init__(
            self,
            app: ASGIApp,
            max_requests: int = 100,
            window_seconds: int = 60,
            exempt_paths: Optional[list] = None
    ):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.exempt_paths = exempt_paths or ["/health", "/api/docs", "/api/redoc", "/static"]

        # In-memory хранилище (fallback)
        self.request_counts = defaultdict(list)

    async def dispatch(
            self, request: Request, call_next: Callable
    ) -> Response:
        # Проверяем, нужно ли применять rate limiting
        if any(request.url.path.startswith(path) for path in self.exempt_paths):
            return await call_next(request)

        # Определяем клиента (IP или user_id)
        client_id = self._get_client_id(request)

        # Проверяем лимит
        is_allowed, remaining, reset_time = await self._check_rate_limit(client_id)

        if not is_allowed:
            # Логируем превышение лимита
            log_security_event(
                "rate_limit_exceeded",
                user_id=getattr(request.state, "user", None),
                ip_address=client_id,
                details={
                    "path": request.url.path,
                    "method": request.method
                }
            )

            logger.warning(
                f"Rate limit exceeded for {client_id}",
                extra={
                    "client_id": client_id,
                    "path": request.url.path
                }
            )

            # Возвращаем 429 Too Many Requests
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Слишком много запросов. Попробуйте позже.",
                headers={
                    "X-RateLimit-Limit": str(self.max_requests),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                    "Retry-After": str(int(reset_time - time.time()))
                }
            )

        # Обрабатываем запрос
        response = await call_next(request)

        # Добавляем заголовки rate limit
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)

        return response

    def _get_client_id(self, request: Request) -> str:
        """Определить ID клиента для rate limiting"""

        # Если пользователь авторизован, используем user_id
        if hasattr(request.state, "user") and request.state.user:
            return f"user:{request.state.user.id}"

        # Иначе используем IP
        client_ip = getattr(request.state, "client_ip", None)
        if not client_ip and request.client:
            client_ip = request.client.host

        return f"ip:{client_ip or 'unknown'}"

    async def _check_rate_limit(
            self, client_id: str
    ) -> tuple[bool, int, int]:
        """
        Проверить rate limit

        Returns:
            (is_allowed, remaining_requests, reset_timestamp)
        """

        # Пробуем использовать Redis
        if cache_manager.is_connected():
            return await self._check_rate_limit_redis(client_id)
        else:
            return self._check_rate_limit_memory(client_id)

    async def _check_rate_limit_redis(
            self, client_id: str
    ) -> tuple[bool, int, int]:
        """Rate limiting через Redis (для distributed системы)"""

        key = f"rate_limit:{client_id}"
        current_time = time.time()

        try:
            # Используем Redis sorted set для хранения timestamps
            pipe = cache_manager.redis_client.pipeline()

            # Удаляем старые записи
            window_start = current_time - self.window_seconds
            pipe.zremrangebyscore(key, 0, window_start)

            # Получаем текущее количество запросов
            pipe.zcard(key)

            # Добавляем новую запись
            pipe.zadd(key, {str(current_time): current_time})

            # Устанавливаем TTL
            pipe.expire(key, self.window_seconds)

            results = await pipe.execute()
            current_count = results[1]  # Результат zcard

            # Проверяем лимит
            is_allowed = current_count < self.max_requests
            remaining = max(0, self.max_requests - current_count - 1)
            reset_time = int(current_time + self.window_seconds)

            return is_allowed, remaining, reset_time

        except Exception as e:
            logger.error(f"Redis rate limit error: {e}")
            # Fallback на memory
            return self._check_rate_limit_memory(client_id)

    def _check_rate_limit_memory(
            self, client_id: str
    ) -> tuple[bool, int, int]:
        """Rate limiting через память (только для single instance)"""

        current_time = time.time()
        window_start = current_time - self.window_seconds

        # Получаем записи для клиента
        requests = self.request_counts[client_id]

        # Удаляем старые записи
        requests = [t for t in requests if t > window_start]
        self.request_counts[client_id] = requests

        # Проверяем лимит
        current_count = len(requests)
        is_allowed = current_count < self.max_requests

        if is_allowed:
            requests.append(current_time)

        remaining = max(0, self.max_requests - current_count - 1)

        # Вычисляем время сброса (самая старая запись + окно)
        if requests:
            reset_time = int(min(requests) + self.window_seconds)
        else:
            reset_time = int(current_time + self.window_seconds)

        return is_allowed, remaining, reset_time


class EndpointRateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware для разных лимитов на разных endpoints

    Позволяет настроить индивидуальные лимиты для разных маршрутов
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

        # Конфигурация лимитов для разных endpoints
        self.limits = {
            # Auth endpoints - строгие лимиты
            "/api/auth/login": {"max_requests": 5, "window": 60},
            "/api/auth/register": {"max_requests": 3, "window": 300},

            # Submission endpoints - умеренные лимиты
            "/api/submissions/submit": {"max_requests": 10, "window": 60},

            # Shop endpoints - средние лимиты
            "/api/shop/purchase": {"max_requests": 20, "window": 60},

            # По умолчанию
            "default": {"max_requests": 100, "window": 60}
        }

    async def dispatch(
            self, request: Request, call_next: Callable
    ) -> Response:
        # Определяем endpoint
        path = request.url.path

        # Ищем подходящий лимит
        limit_config = None
        for endpoint, config in self.limits.items():
            if endpoint != "default" and path.startswith(endpoint):
                limit_config = config
                break

        # Используем лимит по умолчанию
        if not limit_config:
            limit_config = self.limits["default"]

        # Проверяем rate limit
        client_id = self._get_client_id(request)
        key = f"rate_limit:{path}:{client_id}"

        is_allowed = await self._check_limit(
            key,
            limit_config["max_requests"],
            limit_config["window"]
        )

        if not is_allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Слишком много запросов к {path}. Попробуйте позже."
            )

        return await call_next(request)

    def _get_client_id(self, request: Request) -> str:
        """Определить ID клиента"""
        if hasattr(request.state, "user") and request.state.user:
            return f"user:{request.state.user.id}"

        client_ip = getattr(request.state, "client_ip", None)
        if not client_ip and request.client:
            client_ip = request.client.host

        return f"ip:{client_ip or 'unknown'}"

    async def _check_limit(
            self, key: str, max_requests: int, window: int
    ) -> bool:
        """Проверить лимит для конкретного ключа"""

        if cache_manager.is_connected():
            try:
                # Инкрементируем счетчик
                count = await cache_manager.increment(key, window)
                return count <= max_requests
            except:
                # При ошибке разрешаем запрос
                return True

        # Без Redis разрешаем все (для development)
        return True


class IPWhitelistMiddleware(BaseHTTPMiddleware):
    """
    Middleware для белого списка IP адресов

    Полезно для admin endpoints
    """

    def __init__(
            self,
            app: ASGIApp,
            whitelist: list[str],
            protected_paths: list[str]
    ):
        super().__init__(app)
        self.whitelist = set(whitelist)
        self.protected_paths = protected_paths

    async def dispatch(
            self, request: Request, call_next: Callable
    ) -> Response:
        # Проверяем, защищен ли путь
        is_protected = any(
            request.url.path.startswith(path)
            for path in self.protected_paths
        )

        if not is_protected:
            return await call_next(request)

        # Получаем IP клиента
        client_ip = getattr(request.state, "client_ip", None)
        if not client_ip and request.client:
            client_ip = request.client.host

        # Проверяем белый список
        if client_ip not in self.whitelist:
            log_security_event(
                "unauthorized_ip_access",
                ip_address=client_ip,
                details={"path": request.url.path}
            )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied from your IP address"
            )

        return await call_next(request)


# Экспортируем middleware
__all__ = [
    'RateLimitMiddleware',
    'EndpointRateLimitMiddleware',
    'IPWhitelistMiddleware'
]