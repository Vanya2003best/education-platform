"""
API для работы с монетами и транзакциями
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List
from datetime import datetime, timedelta

from app.database import get_async_db
from app.models import User, Transaction
from app.auth import get_current_user

router = APIRouter()


@router.get("/balance")
async def get_balance(current_user: User = Depends(get_current_user)):
    """
    Получить баланс монет
    """
    return {
        "user_id": current_user.id,
        "username": current_user.username,
        "coins": current_user.coins,
        "level": current_user.level,
        "experience": current_user.experience
    }


@router.get("/transactions")
async def get_transactions(
        skip: int = 0,
        limit: int = 50,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db)
):
    """
    История транзакций
    """
    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == current_user.id)
        .order_by(Transaction.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    transactions = result.scalars().all()

    return [
        {
            "id": t.id,
            "coins_amount": t.coins_amount,
            "type": t.transaction_type,
            "description": t.description,
            "created_at": t.created_at
        }
        for t in transactions
    ]


@router.get("/stats")
async def get_user_stats(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db)
):
    """
    Статистика пользователя
    """
    # Общие заработанные монеты
    total_earned_result = await db.execute(
        select(func.sum(Transaction.coins_amount))
        .where(
            Transaction.user_id == current_user.id,
            Transaction.coins_amount > 0
        )
    )
    total_earned_sum = total_earned_result.scalar() or 0

    # Общие потраченные монеты
    total_spent_result = await db.execute(
        select(func.sum(Transaction.coins_amount))
        .where(
            Transaction.user_id == current_user.id,
            Transaction.coins_amount < 0
        )
    )
    total_spent_sum = abs(total_spent_result.scalar() or 0)

    # Статистика за последние 7 дней
    week_ago = datetime.utcnow() - timedelta(days=7)
    week_earned_result = await db.execute(
        select(func.sum(Transaction.coins_amount))
        .where(
            Transaction.user_id == current_user.id,
            Transaction.coins_amount > 0,
            Transaction.created_at >= week_ago
        )
    )
    week_earned_sum = week_earned_result.scalar() or 0

    # Опыт до следующего уровня
    next_level_exp = calculate_exp_for_level(current_user.level + 1)
    exp_needed = next_level_exp - current_user.experience

    return {
        "total_coins_earned": int(total_earned_sum),
        "total_coins_spent": int(total_spent_sum),
        "current_balance": current_user.coins,
        "week_earned": int(week_earned_sum),
        "level": current_user.level,
        "experience": current_user.experience,
        "exp_to_next_level": exp_needed,
        "tasks_completed": current_user.tasks_completed,
        "average_score": round(current_user.average_score, 1)
    }


@router.get("/leaderboard")
async def get_leaderboard(
        limit: int = 10,
        db: AsyncSession = Depends(get_async_db)
):
    """
    Таблица лидеров по уровню и опыту
    """
    result = await db.execute(
        select(User)
        .where(User.is_active == True)
        .order_by(User.level.desc(), User.experience.desc())
        .limit(limit)
    )
    users = result.scalars().all()

    leaderboard = []
    for rank, user in enumerate(users, start=1):
        leaderboard.append({
            "rank": rank,
            "username": user.username,
            "level": user.level,
            "experience": user.experience,
            "tasks_completed": user.tasks_completed,
            "average_score": round(user.average_score, 1)
        })

    return leaderboard


def calculate_exp_for_level(level: int) -> int:
    """Рассчитать необходимый опыт для достижения уровня"""
    return ((level - 1) ** 2) * 100