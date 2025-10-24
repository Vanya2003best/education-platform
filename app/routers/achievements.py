"""
API для системы достижений
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from typing import List, Optional
from datetime import datetime

from app.database import get_async_db
from app.models import (
    Achievement, UserAchievement, User, Submission,
    Transaction
)
from app.schemas import (
    AchievementResponse, AchievementCreate,
    UserAchievementResponse
)
from app.auth import get_current_user, require_admin
from app.utils.cache import cache_manager, cache_result

router = APIRouter()


@router.get("/", response_model=List[AchievementResponse])
@cache_result("achievements_list", ttl=3600)
async def get_all_achievements(
        category: Optional[str] = None,
        rarity: Optional[str] = None,
        include_hidden: bool = False,
        db: AsyncSession = Depends(get_async_db)
):
    """Получить все достижения"""

    query = select(Achievement).where(Achievement.is_active == True)

    if not include_hidden:
        query = query.where(Achievement.is_hidden == False)

    if category:
        query = query.where(Achievement.category == category)

    if rarity:
        query = query.where(Achievement.rarity == rarity)

    result = await db.execute(query.order_by(Achievement.points.desc()))
    achievements = result.scalars().all()

    return achievements


@router.get("/my", response_model=List[UserAchievementResponse])
async def get_my_achievements(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db)
):
    """Получить свои достижения"""

    result = await db.execute(
        select(UserAchievement)
        .where(UserAchievement.user_id == current_user.id)
        .order_by(UserAchievement.unlocked_at.desc())
    )

    user_achievements = result.scalars().all()

    # Загружаем связанные достижения
    achievement_ids = [ua.achievement_id for ua in user_achievements]
    achievements_result = await db.execute(
        select(Achievement).where(Achievement.id.in_(achievement_ids))
    )
    achievements_map = {a.id: a for a in achievements_result.scalars().all()}

    # Формируем ответ
    response = []
    for ua in user_achievements:
        achievement = achievements_map.get(ua.achievement_id)
        if achievement:
            response.append(
                UserAchievementResponse(
                    achievement=achievement,
                    unlocked_at=ua.unlocked_at,
                    progress=ua.progress,
                    is_claimed=ua.is_claimed
                )
            )

    return response


@router.get("/progress")
async def get_achievements_progress(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db)
):
    """Получить прогресс по всем достижениям"""

    # Получаем все достижения
    achievements_result = await db.execute(
        select(Achievement).where(
            and_(
                Achievement.is_active == True,
                Achievement.is_hidden == False
            )
        )
    )
    all_achievements = achievements_result.scalars().all()

    # Получаем полученные достижения
    unlocked_result = await db.execute(
        select(UserAchievement).where(
            UserAchievement.user_id == current_user.id
        )
    )
    unlocked_map = {ua.achievement_id: ua for ua in unlocked_result.scalars().all()}

    # Формируем прогресс
    progress = []
    for achievement in all_achievements:
        user_achievement = unlocked_map.get(achievement.id)

        if user_achievement:
            progress.append({
                "achievement": achievement,
                "unlocked": True,
                "progress": user_achievement.progress,
                "unlocked_at": user_achievement.unlocked_at,
                "is_claimed": user_achievement.is_claimed
            })
        else:
            # Вычисляем текущий прогресс
            current_progress = await calculate_achievement_progress(
                current_user, achievement, db
            )

            progress.append({
                "achievement": achievement,
                "unlocked": False,
                "progress": current_progress,
                "unlocked_at": None,
                "is_claimed": False
            })

    return {
        "total": len(all_achievements),
        "unlocked": len(unlocked_map),
        "progress": progress
    }


@router.post("/{achievement_id}/claim")
async def claim_achievement_reward(
        achievement_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db)
):
    """Забрать награду за достижение"""

    # Проверяем, получено ли достижение
    result = await db.execute(
        select(UserAchievement).where(
            and_(
                UserAchievement.user_id == current_user.id,
                UserAchievement.achievement_id == achievement_id
            )
        )
    )
    user_achievement = result.scalar_one_or_none()

    if not user_achievement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Достижение не получено"
        )

    if user_achievement.is_claimed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Награда уже получена"
        )

    # Получаем информацию о достижении
    achievement_result = await db.execute(
        select(Achievement).where(Achievement.id == achievement_id)
    )
    achievement = achievement_result.scalar_one()

    # Начисляем награды
    current_user.coins += achievement.reward_coins
    current_user.gems += achievement.reward_gems
    current_user.experience += achievement.reward_exp

    # Помечаем как полученное
    user_achievement.is_claimed = True

    # Создаем транзакцию
    transaction = Transaction(
        user_id=current_user.id,
        coins_amount=achievement.reward_coins,
        gems_amount=achievement.reward_gems,
        exp_amount=achievement.reward_exp,
        transaction_type="achievement",
        category="reward",
        description=f"Награда за достижение: {achievement.name}",
        coins_balance=current_user.coins,
        gems_balance=current_user.gems
    )
    db.add(transaction)

    await db.commit()

    return {
        "message": "Награда получена!",
        "rewards": {
            "coins": achievement.reward_coins,
            "gems": achievement.reward_gems,
            "exp": achievement.reward_exp
        }
    }


@router.post("/check")
async def check_new_achievements(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db)
):
    """Проверить новые достижения"""

    # Получаем все активные достижения
    achievements_result = await db.execute(
        select(Achievement).where(Achievement.is_active == True)
    )
    all_achievements = achievements_result.scalars().all()

    # Получаем уже полученные
    unlocked_result = await db.execute(
        select(UserAchievement.achievement_id).where(
            UserAchievement.user_id == current_user.id
        )
    )
    unlocked_ids = set(row[0] for row in unlocked_result.all())

    # Проверяем каждое достижение
    newly_unlocked = []

    for achievement in all_achievements:
        if achievement.id in unlocked_ids:
            continue

        # Проверяем критерии
        if await check_achievement_criteria(current_user, achievement, db):
            # Разблокируем достижение
            user_achievement = UserAchievement(
                user_id=current_user.id,
                achievement_id=achievement.id,
                unlocked_at=datetime.utcnow(),
                progress=100,
                is_claimed=False
            )
            db.add(user_achievement)
            newly_unlocked.append(achievement)

    if newly_unlocked:
        await db.commit()

    return {
        "new_achievements": len(newly_unlocked),
        "achievements": [
            {
                "id": a.id,
                "name": a.name,
                "description": a.description,
                "icon_url": a.icon_url,
                "rarity": a.rarity
            }
            for a in newly_unlocked
        ]
    }


@router.post("/", response_model=AchievementResponse)
async def create_achievement(
        achievement_data: AchievementCreate,
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Создать новое достижение (только для админов)"""

    achievement = Achievement(
        name=achievement_data.name,
        description=achievement_data.description,
        icon_url=achievement_data.icon_url,
        category=achievement_data.category,
        rarity=achievement_data.rarity,
        criteria=achievement_data.criteria,
        points=achievement_data.points,
        reward_coins=achievement_data.reward_coins,
        reward_gems=achievement_data.reward_gems,
        reward_exp=achievement_data.reward_exp,
        is_hidden=achievement_data.is_hidden
    )

    db.add(achievement)
    await db.commit()
    await db.refresh(achievement)

    # Инвалидируем кэш
    await cache_manager.delete("achievements_list")

    return achievement


@router.get("/categories")
async def get_achievement_categories(
        db: AsyncSession = Depends(get_async_db)
):
    """Получить доступные категории"""

    result = await db.execute(
        select(Achievement.category).distinct()
    )

    categories = [row[0] for row in result.all() if row[0]]

    return categories


# Вспомогательные функции

async def check_achievement_criteria(
        user: User,
        achievement: Achievement,
        db: AsyncSession
) -> bool:
    """Проверить, выполнены ли критерии достижения"""

    if not achievement.criteria:
        return False

    criteria = achievement.criteria

    # Проверяем различные типы критериев
    if "tasks_completed" in criteria:
        if user.tasks_completed < criteria["tasks_completed"]:
            return False

    if "min_level" in criteria:
        if user.level < criteria["min_level"]:
            return False

    if "min_score" in criteria:
        # Проверяем, есть ли работа с таким баллом
        result = await db.execute(
            select(Submission).where(
                and_(
                    Submission.user_id == user.id,
                    Submission.score >= criteria["min_score"]
                )
            ).limit(1)
        )
        if not result.scalar_one_or_none():
            return False

    if "perfect_scores" in criteria:
        # Количество идеальных работ (100 баллов)
        count = await db.scalar(
            select(func.count(Submission.id)).where(
                and_(
                    Submission.user_id == user.id,
                    Submission.score == 100
                )
            )
        )
        if count < criteria["perfect_scores"]:
            return False

    if "streak_days" in criteria:
        if user.streak_days < criteria["streak_days"]:
            return False

    if "coins_earned" in criteria:
        # Считаем заработанные монеты
        total = await db.scalar(
            select(func.sum(Transaction.coins_amount)).where(
                and_(
                    Transaction.user_id == user.id,
                    Transaction.coins_amount > 0
                )
            )
        )
        if (total or 0) < criteria["coins_earned"]:
            return False

    # Все критерии выполнены
    return True


async def calculate_achievement_progress(
        user: User,
        achievement: Achievement,
        db: AsyncSession
) -> int:
    """Вычислить текущий прогресс достижения (0-100)"""

    if not achievement.criteria:
        return 0

    criteria = achievement.criteria
    progress_parts = []

    # Считаем прогресс по каждому критерию
    if "tasks_completed" in criteria:
        progress = min(100, int(user.tasks_completed / criteria["tasks_completed"] * 100))
        progress_parts.append(progress)

    if "min_level" in criteria:
        progress = min(100, int(user.level / criteria["min_level"] * 100))
        progress_parts.append(progress)

    if "perfect_scores" in criteria:
        count = await db.scalar(
            select(func.count(Submission.id)).where(
                and_(
                    Submission.user_id == user.id,
                    Submission.score == 100
                )
            )
        )
        progress = min(100, int((count or 0) / criteria["perfect_scores"] * 100))
        progress_parts.append(progress)

    if "streak_days" in criteria:
        progress = min(100, int(user.streak_days / criteria["streak_days"] * 100))
        progress_parts.append(progress)

    # Возвращаем средний прогресс
    if progress_parts:
        return int(sum(progress_parts) / len(progress_parts))

    return 0