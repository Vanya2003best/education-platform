"""
Кэширование с Redis для улучшения производительности
"""
import json
import pickle
from typing import Optional, Any, Union
from datetime import timedelta
import redis.asyncio as redis
from functools import wraps
import hashlib
import logging

from app.config import settings

logger = logging.getLogger(__name__)


class CacheManager:
    """Менеджер кэширования с Redis"""

    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self._connected = False

    async def connect(self):
        """Подключение к Redis"""
        if not settings.REDIS_URL:
            logger.warning("Redis URL not configured, caching disabled")
            return

        try:
            self.redis_client = redis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True
            )
            await self.redis_client.ping()
            self._connected = True
            logger.info("Connected to Redis successfully")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._connected = False

    async def disconnect(self):
        """Отключение от Redis"""
        if self.redis_client:
            await self.redis_client.close()
            self._connected = False

    def is_connected(self) -> bool:
        """Проверка подключения"""
        return self._connected

    async def get(self, key: str) -> Optional[Any]:
        """Получить значение из кэша"""
        if not self._connected:
            return None

        try:
            value = await self.redis_client.get(key)
            if value:
                # Пробуем десериализовать JSON
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    # Если не JSON, возвращаем как есть
                    return value
        except Exception as e:
            logger.error(f"Cache get error: {e}")

        return None

    async def set(
            self,
            key: str,
            value: Any,
            ttl: Optional[int] = None
    ) -> bool:
        """Сохранить значение в кэш"""
        if not self._connected:
            return False

        try:
            # Сериализуем в JSON если возможно
            if isinstance(value, (dict, list)):
                value = json.dumps(value)
            elif not isinstance(value, str):
                value = str(value)

            ttl = ttl or settings.REDIS_TTL
            await self.redis_client.setex(key, ttl, value)
            return True
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Удалить значение из кэша"""
        if not self._connected:
            return False

        try:
            await self.redis_client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return False

    async def exists(self, key: str) -> bool:
        """Проверить существование ключа"""
        if not self._connected:
            return False

        try:
            return bool(await self.redis_client.exists(key))
        except Exception as e:
            logger.error(f"Cache exists error: {e}")
            return False

    async def increment(self, key: str, ttl: Optional[int] = None) -> int:
        """Инкремент счетчика"""
        if not self._connected:
            return 0

        try:
            pipeline = self.redis_client.pipeline()
            pipeline.incr(key)
            if ttl:
                pipeline.expire(key, ttl)
            results = await pipeline.execute()
            return results[0]
        except Exception as e:
            logger.error(f"Cache increment error: {e}")
            return 0

    async def get_or_set(
            self,
            key: str,
            factory,
            ttl: Optional[int] = None
    ) -> Any:
        """Получить из кэша или вычислить и сохранить"""
        # Пробуем получить из кэша
        value = await self.get(key)
        if value is not None:
            return value

        # Вычисляем значение
        if callable(factory):
            value = await factory() if hasattr(factory, '__await__') else factory()
        else:
            value = factory

        # Сохраняем в кэш
        await self.set(key, value, ttl)

        return value

    async def invalidate_pattern(self, pattern: str) -> int:
        """Удалить все ключи по паттерну"""
        if not self._connected:
            return 0

        try:
            keys = await self.redis_client.keys(pattern)
            if keys:
                return await self.redis_client.delete(*keys)
        except Exception as e:
            logger.error(f"Cache invalidate pattern error: {e}")

        return 0

    # Методы для работы со списками
    async def lpush(self, key: str, *values) -> int:
        """Добавить в начало списка"""
        if not self._connected:
            return 0

        try:
            return await self.redis_client.lpush(key, *values)
        except Exception as e:
            logger.error(f"Cache lpush error: {e}")
            return 0

    async def lrange(self, key: str, start: int = 0, end: int = -1) -> list:
        """Получить диапазон из списка"""
        if not self._connected:
            return []

        try:
            return await self.redis_client.lrange(key, start, end)
        except Exception as e:
            logger.error(f"Cache lrange error: {e}")
            return []

    # Методы для работы с множествами
    async def sadd(self, key: str, *values) -> int:
        """Добавить в множество"""
        if not self._connected:
            return 0

        try:
            return await self.redis_client.sadd(key, *values)
        except Exception as e:
            logger.error(f"Cache sadd error: {e}")
            return 0

    async def sismember(self, key: str, value: str) -> bool:
        """Проверить принадлежность множеству"""
        if not self._connected:
            return False

        try:
            return bool(await self.redis_client.sismember(key, value))
        except Exception as e:
            logger.error(f"Cache sismember error: {e}")
            return False

    # Специализированные методы
    async def cache_user_session(self, user_id: int, data: dict, ttl: int = 3600) -> bool:
        """Кэшировать сессию пользователя"""
        key = f"session:{user_id}"
        return await self.set(key, data, ttl)

    async def get_user_session(self, user_id: int) -> Optional[dict]:
        """Получить сессию пользователя"""
        key = f"session:{user_id}"
        return await self.get(key)

    async def is_token_blacklisted(self, jti: str) -> bool:
        """Проверить, отозван ли токен"""
        key = f"blacklist:{jti}"
        return await self.exists(key)

    async def blacklist_token(self, jti: str, ttl: int = 86400) -> bool:
        """Добавить токен в черный список"""
        key = f"blacklist:{jti}"
        return await self.set(key, "1", ttl)

    async def cache_leaderboard(self, data: list, ttl: int = 300) -> bool:
        """Кэшировать таблицу лидеров"""
        return await self.set("leaderboard", data, ttl)

    async def get_leaderboard(self) -> Optional[list]:
        """Получить таблицу лидеров"""
        return await self.get("leaderboard")


# Глобальный экземпляр
cache_manager = CacheManager()


def cache_result(key_prefix: str, ttl: int = 300):
    """
    Декоратор для кэширования результатов функций

    Usage:
        @cache_result("tasks", ttl=600)
        async def get_tasks(subject: str):
            ...
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Генерируем ключ на основе аргументов
            cache_key = f"{key_prefix}:{_generate_cache_key(args, kwargs)}"

            # Пробуем получить из кэша
            cached = await cache_manager.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for {cache_key}")
                return cached

            # Вычисляем результат
            result = await func(*args, **kwargs)

            # Сохраняем в кэш
            await cache_manager.set(cache_key, result, ttl)
            logger.debug(f"Cache miss for {cache_key}, cached for {ttl}s")

            return result

        return wrapper

    return decorator


def _generate_cache_key(args: tuple, kwargs: dict) -> str:
    """Генерация ключа кэша на основе аргументов"""
    # Создаем строку из аргументов
    key_parts = []

    # Добавляем позиционные аргументы
    for arg in args:
        if isinstance(arg, (str, int, float, bool)):
            key_parts.append(str(arg))
        elif hasattr(arg, 'id'):
            key_parts.append(f"{type(arg).__name__}:{arg.id}")

    # Добавляем именованные аргументы
    for k, v in sorted(kwargs.items()):
        if isinstance(v, (str, int, float, bool)):
            key_parts.append(f"{k}:{v}")

    # Создаем хеш для компактности
    key_string = ":".join(key_parts)
    return hashlib.md5(key_string.encode()).hexdigest()


class CacheKeys:
    """Константы для ключей кэша"""

    # Пользователи
    USER = "user:{user_id}"
    USER_STATS = "user:stats:{user_id}"
    USER_SESSION = "session:{user_id}"

    # Задания
    TASK = "task:{task_id}"
    TASKS_LIST = "tasks:list:{filters_hash}"
    TASK_STATS = "task:stats:{task_id}"

    # Сдачи
    SUBMISSION = "submission:{submission_id}"
    USER_SUBMISSIONS = "submissions:user:{user_id}"

    # Магазин
    SHOP_ITEMS = "shop:items:{category}"
    USER_PURCHASES = "purchases:user:{user_id}"

    # Лидерборды
    LEADERBOARD_GLOBAL = "leaderboard:global"
    LEADERBOARD_WEEKLY = "leaderboard:weekly"
    LEADERBOARD_SUBJECT = "leaderboard:subject:{subject}"

    # Rate limiting
    RATE_LIMIT = "rate:{client_id}:{endpoint}"

    # Токены
    TOKEN_BLACKLIST = "blacklist:{jti}"
    REFRESH_TOKEN = "refresh:{user_id}:{jti}"