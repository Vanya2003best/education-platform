"""
Education Platform v2.0 - Главный файл приложения
Образовательная платформа с AI-проверкой работ
"""
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.encoders import jsonable_encoder
from collections.abc import Mapping
from fastapi.encoders import jsonable_encoder
from typing import Any
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Match
from contextlib import asynccontextmanager
import uvicorn
import os
import logging
import time
from prometheus_client import make_asgi_app, Counter, Histogram, Gauge
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from app.config import settings
from app.database import init_db, close_db, async_engine
from app.models import Base
from app.utils.cache import cache_manager
from app.middleware.logging import LoggingMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.utils.logger import setup_logging

# Импорт роутеров
from app.routers import (
    admin,
    tasks,
    auth,
    submissions,
    coins,
    shop,
    users,
    achievements,
    analytics,
)

# Настройка логирования
logger = setup_logging()

# Метрики Prometheus
request_count = Counter('app_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
request_duration = Histogram('app_request_duration_seconds', 'Request duration')
active_users = Gauge('app_active_users', 'Active users count')
submission_processing = Histogram('submission_processing_seconds', 'Submission processing time')


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    # Startup
    logger.info("Starting Education Platform v2.0...")

    # Инициализация БД
    await init_db()
    logger.info("Database initialized")

    # Подключение к Redis
    await cache_manager.connect()
    if cache_manager.is_connected():
        logger.info("Redis connected")
    else:
        logger.warning("Redis not available, running without cache")

    # Инициализация Sentry для production
    if settings.SENTRY_DSN and settings.is_production:
        sentry_sdk.init(
            dsn=settings.SENTRY_DSN,
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlalchemyIntegration(),
            ],
            traces_sample_rate=0.1,
            environment=settings.ENVIRONMENT,
            release=settings.APP_VERSION,
        )
        logger.info("Sentry monitoring initialized")

    logger.info("Application started successfully")

    yield

    # Shutdown
    logger.info("Shutting down Education Platform...")

    # Закрываем соединения
    await cache_manager.disconnect()
    await close_db()

    logger.info("Application shutdown complete")


# Создание приложения
app = FastAPI(
    title="Education Platform API",
    redirect_slashes=True,
    description="AI-powered educational platform for handwriting assessment",
    version=settings.APP_VERSION,
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url="/api/redoc" if not settings.is_production else None,
    lifespan=lifespan
)

# --- CORS настройки ---

cors_kwargs = dict(
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=["OPTIONS", "GET", "POST", "PATCH", "DELETE", "HEAD"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Page", "X-Per-Page"],
)

effective_origins = set(getattr(settings, "effective_cors_origins", []) or [])
required_local_origins = {"http://localhost:8000", "http://127.0.0.1:8000"}

allow_origins = sorted(effective_origins.union(required_local_origins)) or list(required_local_origins)
allow_origins: list[str] = []
if effective_origins:
    allow_origins.extend(effective_origins)
for required_origin in required_local_origins:
    if required_origin not in allow_origins:
        allow_origins.append(required_origin)

if allow_origins:
    cors_kwargs["allow_origins"] = allow_origins
else:
    cors_kwargs["allow_origins"] = list(required_local_origins)

if settings.cors_allow_all:
    cors_kwargs["allow_origin_regex"] = r"https?://(localhost|127\.0\.0\.1)(:\d+)?$"

app.add_middleware(CORSMiddleware, **cors_kwargs)

# Сжатие ответов
app.add_middleware(GZipMiddleware, minimum_size=1000)


if getattr(settings, "RATE_LIMIT_REQUESTS", 0):
    app.add_middleware(RateLimitMiddleware, max_requests=settings.RATE_LIMIT_REQUESTS)

from fastapi.responses import JSONResponse
import traceback, logging

logger = logging.getLogger(__name__)

@app.exception_handler(Exception)
async def unhandled_exc_handler(request: Request, exc: Exception):
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    logger.error("UNHANDLED %s %s -> %s\n%s", request.method, request.url.path, repr(exc), tb)
    # Возвращаем JSON вместо голого текста:
    return JSONResponse(status_code=500, content={"detail": "Internal Server Error", "error": repr(exc)})

# Безопасность - проверка хоста
if settings.is_production:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*.education-platform.com", "localhost"]
    )

# Кастомные middleware
app.add_middleware(LoggingMiddleware)

# Подключение роутеров с префиксами и тегами
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(auth.router, prefix="/api/auth", tags=["🔐 Authentication"])
app.include_router(users.router, prefix="/api/users", tags=["👤 Users"])
app.include_router(submissions.router, prefix="/api/submissions", tags=["📸 Submissions"])
app.include_router(coins.router, prefix="/api/coins", tags=["💰 Coins & Economy"])
app.include_router(shop.router, prefix="/api/shop", tags=["🛍️ Shop"])
app.include_router(achievements.router, prefix="/api/achievements", tags=["🏆 Achievements"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["📊 Analytics"])

# Автоматический редирект между /path и /path/
app.router.redirect_slashes = True

# Временный дамп маршрутов для отладки
for route in app.router.routes:
    try:
        print("ROUTE:", route.path, getattr(route, "methods", None))
    except Exception:
        pass

# Статические файлы
os.makedirs("uploads/submissions", exist_ok=True)
os.makedirs("static", exist_ok=True)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Prometheus метрики endpoint
if settings.PROMETHEUS_ENABLED:
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)


def _describe_route_matches(request: Request) -> list[dict[str, Any]]:
    """Return router matches for debugging 404/405 issues."""

    scope = dict(request.scope)
    scope.setdefault("path", request.url.path)
    scope.setdefault("method", request.method)

    matches: list[dict[str, Any]] = []
    for route in request.app.router.routes:
        matcher = getattr(route, "matches", None)
        if matcher is None:
            continue
        try:
            match, _ = matcher(scope)
        except Exception:  # pragma: no cover - defensive logging helper
            continue
        if match is Match.NONE:
            continue
        methods = sorted(route.methods or []) if getattr(route, "methods", None) else []
        matches.append(
            {
                "path": getattr(route, "path", None),
                "methods": methods,
                "match": match.name,
                "name": getattr(route, "name", None),
            }
        )
    return matches


# Обработчики ошибок
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Обработчик HTTP исключений"""
    headers = exc.headers or None
    route_matches = _describe_route_matches(request)
    logger.warning(
        "HTTPException encountered",
        extra={
            "status_code": exc.status_code,
            "method": request.method,
            "path": request.url.path,
            "detail": exc.detail,
            "matches": route_matches,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "message": exc.detail,
                "status_code": exc.status_code,
                "path": request.url.path,
                "method": request.method,
                "timestamp": time.time()
            }
        },
        headers=headers,
    )
def _stringify_exceptions(value):
    """Рекурсивно преобразует исключения в сериализуемые значения."""
    if isinstance(value, BaseException):
        message = str(value)
        return message or value.__class__.__name__
    if isinstance(value, Mapping):
        return {key: _stringify_exceptions(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_stringify_exceptions(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_stringify_exceptions(item) for item in value)
    if isinstance(value, set):
        sanitized = [_stringify_exceptions(item) for item in value]
        try:
            return sorted(sanitized, key=lambda item: repr(item))
        except TypeError:  # pragma: no cover - гетерогенные структуры без порядка
            return sanitized
    return value

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Обработчик ошибок валидации"""
    sanitized_errors = _stringify_exceptions(exc.errors())
    error_details = jsonable_encoder(sanitized_errors)
    body_payload = None
    if settings.DEBUG and exc.body is not None:
        body_payload = jsonable_encoder(_stringify_exceptions(exc.body))

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={
            "error": {
                "message": "Validation error",
                "details": error_details,
                "body": body_payload,
            }
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Обработчик всех остальных исключений"""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    # В production скрываем детали ошибки
    if settings.is_production:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "message": "Internal server error",
                    "status_code": 500
                }
            }
        )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "message": str(exc),
                "type": type(exc).__name__,
                "status_code": 500
            }
        }
    )


# Middleware для метрик
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Сбор метрик для Prometheus"""
    start_time = time.time()

    # Обработка запроса
    response = await call_next(request)

    # Записываем метрики
    duration = time.time() - start_time
    request_duration.observe(duration)
    request_count.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()

    # Добавляем заголовки с информацией о времени
    response.headers["X-Response-Time"] = f"{duration:.3f}"

    return response


# Основные endpoints
@app.get("/", tags=["General"])
async def root():
    """Перенаправление на документацию или UI"""
    if settings.is_production:
        return RedirectResponse(url="/static/index.html")
    return RedirectResponse(url="/api/docs")


@app.get("/api", tags=["General"])
async def api_info():
    """Информация об API"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "features": {
            "ai_checking": settings.FEATURE_AI_CHECKING,
            "email_notifications": settings.FEATURE_EMAIL_NOTIFICATIONS,
            "social_login": settings.FEATURE_SOCIAL_LOGIN,
            "achievements": settings.FEATURE_ACHIEVEMENTS,
            "leaderboard": settings.FEATURE_LEADERBOARD,
        },
        "docs": "/api/docs" if not settings.is_production else None,
        "status": "operational"
    }


@app.get("/health", tags=["Monitoring"])
async def health_check():
    """Проверка здоровья сервиса"""
    checks = {
        "status": "healthy",
        "timestamp": time.time(),
        "version": settings.APP_VERSION,
        "checks": {}
    }

    # Проверка БД
    try:
        async with async_engine.connect() as conn:
            await conn.execute("SELECT 1")
        checks["checks"]["database"] = "ok"
    except Exception as e:
        checks["checks"]["database"] = f"error: {str(e)}"
        checks["status"] = "degraded"

    # Проверка Redis
    if cache_manager.is_connected():
        try:
            await cache_manager.set("health_check", "ok", ttl=10)
            checks["checks"]["cache"] = "ok"
        except:
            checks["checks"]["cache"] = "error"
            checks["status"] = "degraded"
    else:
        checks["checks"]["cache"] = "not configured"

    # Проверка AI сервиса
    checks["checks"]["ai_service"] = "ok" if settings.OPENAI_API_KEY else "not configured"

    # Возвращаем соответствующий статус код
    status_code = status.HTTP_200_OK if checks["status"] == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(content=checks, status_code=status_code)


@app.get("/api/status", tags=["Monitoring"])
async def system_status():
    """Детальный статус системы"""
    from app.utils.monitoring import get_system_metrics

    metrics = await get_system_metrics()

    return {
        "status": "operational",
        "metrics": metrics,
        "uptime": time.time(),  # В production использовать реальный uptime
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT
    }


# Запуск приложения
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))

    if settings.is_production:
        # Production с Gunicorn обрабатывается в Dockerfile
        logger.info("Running in production mode")
    else:
        # Development режим
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=port,
            reload=True,
            log_config={
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {
                    "default": {
                        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    },
                },
                "handlers": {
                    "default": {
                        "formatter": "default",
                        "class": "logging.StreamHandler",
                        "stream": "ext://sys.stdout",
                    },
                },
                "root": {
                    "level": settings.LOG_LEVEL,
                    "handlers": ["default"],
                },
            }
        )