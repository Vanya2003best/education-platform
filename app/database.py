"""
Подключение к базе данных с поддержкой async и пулом соединений
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool
from typing import AsyncGenerator, Generator
import logging

from app.config import settings

logger = logging.getLogger(__name__)

# Исправляем URL для Railway
DATABASE_URL = settings.DATABASE_URL
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Синхронный engine для миграций и seed
sync_engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    echo=settings.DEBUG,
)

# Асинхронный engine для основной работы
async_database_url = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
async_engine = create_async_engine(
    async_database_url,
    pool_pre_ping=True,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    echo=settings.DEBUG,
    # Используем NullPool для serverless окружений
    poolclass=NullPool if settings.ENVIRONMENT == "production" else None,
)

# Фабрики сессий
SessionLocal = sessionmaker(
    bind=sync_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False
)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency для получения синхронной сессии БД
    Используется в FastAPI endpoints
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database session error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency для получения асинхронной сессии БД
    Рекомендуется для production
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            logger.error(f"Async database session error: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Инициализация базы данных"""
    from app.models import Base

    async with async_engine.begin() as conn:
        # Создаем таблицы если их нет
        await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialized successfully")


async def close_db():
    """Закрытие соединений с БД"""
    await async_engine.dispose()
    logger.info("Database connections closed")


class DatabaseManager:
    """Менеджер для работы с транзакциями"""

    def __init__(self):
        self.session = None

    async def __aenter__(self):
        self.session = AsyncSessionLocal()
        return self.session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            await self.session.rollback()
        else:
            await self.session.commit()
        await self.session.close()

    @staticmethod
    async def execute_in_transaction(func, *args, **kwargs):
        """Выполнить функцию в транзакции"""
        async with DatabaseManager() as session:
            return await func(session, *args, **kwargs)