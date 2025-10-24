"""
Мониторинг системных метрик
"""
import psutil
import asyncio
from typing import Dict, Any
from sqlalchemy import select, func

from app.database import async_engine
from app.models import User, Task, Submission
from app.utils.cache import cache_manager


async def get_system_metrics() -> Dict[str, Any]:
    """Получить системные метрики"""

    metrics = {
        "system": get_system_info(),
        "database": await get_database_metrics(),
        "cache": await get_cache_metrics(),
        "application": await get_application_metrics()
    }

    return metrics


def get_system_info() -> Dict[str, Any]:
    """Информация о системе"""
    return {
        "cpu": {
            "percent": psutil.cpu_percent(interval=1),
            "count": psutil.cpu_count(),
            "freq": psutil.cpu_freq().current if psutil.cpu_freq() else 0
        },
        "memory": {
            "total": psutil.virtual_memory().total,
            "available": psutil.virtual_memory().available,
            "percent": psutil.virtual_memory().percent,
            "used": psutil.virtual_memory().used
        },
        "disk": {
            "total": psutil.disk_usage('/').total,
            "used": psutil.disk_usage('/').used,
            "free": psutil.disk_usage('/').free,
            "percent": psutil.disk_usage('/').percent
        },
        "network": {
            "bytes_sent": psutil.net_io_counters().bytes_sent,
            "bytes_recv": psutil.net_io_counters().bytes_recv,
            "packets_sent": psutil.net_io_counters().packets_sent,
            "packets_recv": psutil.net_io_counters().packets_recv
        }
    }


async def get_database_metrics() -> Dict[str, Any]:
    """Метрики базы данных"""
    try:
        async with async_engine.connect() as conn:
            # Подсчет записей
            users_count = await conn.scalar(select(func.count(User.id)))
            tasks_count = await conn.scalar(select(func.count(Task.id)))
            submissions_count = await conn.scalar(select(func.count(Submission.id)))

            # Активные пользователи (за последние 24 часа)
            from datetime import datetime, timedelta
            active_users = await conn.scalar(
                select(func.count(User.id)).where(
                    User.last_activity > datetime.utcnow() - timedelta(days=1)
                )
            )

            return {
                "status": "connected",
                "users_total": users_count,
                "tasks_total": tasks_count,
                "submissions_total": submissions_count,
                "active_users_24h": active_users,
                "pool_size": async_engine.pool.size() if hasattr(async_engine, 'pool') else 0
            }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


async def get_cache_metrics() -> Dict[str, Any]:
    """Метрики кэша"""
    if not cache_manager.is_connected():
        return {"status": "disconnected"}

    try:
        # Получаем информацию о Redis
        info = await cache_manager.redis_client.info()

        return {
            "status": "connected",
            "used_memory": info.get("used_memory_human", "0"),
            "connected_clients": info.get("connected_clients", 0),
            "total_commands": info.get("total_commands_processed", 0),
            "keyspace_hits": info.get("keyspace_hits", 0),
            "keyspace_misses": info.get("keyspace_misses", 0),
            "hit_rate": calculate_hit_rate(
                info.get("keyspace_hits", 0),
                info.get("keyspace_misses", 0)
            )
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }


async def get_application_metrics() -> Dict[str, Any]:
    """Метрики приложения"""
    from datetime import datetime

    # Здесь можно добавить счетчики из Prometheus
    return {
        "timestamp": datetime.utcnow().isoformat(),
        "features": {
            "ai_checking": "enabled",
            "cache": "enabled" if cache_manager.is_connected() else "disabled",
            "email": "disabled"  # TODO: проверить email сервис
        }
    }


def calculate_hit_rate(hits: int, misses: int) -> float:
    """Расчет hit rate для кэша"""
    total = hits + misses
    if total == 0:
        return 0.0
    return round(hits / total * 100, 2)