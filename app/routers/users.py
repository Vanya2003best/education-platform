"""
API для управления пользователями и профилями
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from typing import List, Optional
from datetime import datetime, timedelta
import os

from app.database import get_async_db
from app.models import User, Submission, Purchase, Transaction, UserRole
from app.schemas import (
    UserResponse, UserUpdate, UserStats, PasswordChange,
    TransactionResponse
)
from app.auth import (
    get_current_user, get_current_active_user,
    require_admin, AuthService
)
from app.utils.cache import cache_manager, cache_result
from app.config import settings

router = APIRouter()


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(
        current_user: User = Depends(get_current_active_user)
):
    """Получить свой профиль"""
    return current_user


@router.put("/me", response_model=UserResponse)
async def update_profile(
        updates: UserUpdate,
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_async_db)
):
    """Обновить свой профиль"""

    # Обновляем только переданные поля
    update_data = updates.dict(exclude_unset=True)

    for field, value in update_data.items():
        setattr(current_user, field, value)

    current_user.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(current_user)

    # Инвалидируем кэш
    await cache_manager.delete(f"user:{current_user.id}")

    return current_user


@router.post("/me/password")
async def change_password(
        password_data: PasswordChange,
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_async_db)
):
    """Изменить пароль"""

    # Проверяем старый пароль
    if not AuthService.verify_password(password_data.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Неправильный текущий пароль"
        )

    # Валидируем новый пароль
    is_valid, error_msg = AuthService.validate_password_strength(password_data.new_password)
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )

    # Обновляем пароль
    current_user.password_hash = AuthService.get_password_hash(password_data.new_password)
    current_user.updated_at = datetime.utcnow()

    await db.commit()

    return {"message": "Пароль успешно изменен"}


@router.post("/me/avatar")
async def upload_avatar(
        file: UploadFile = File(...),
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_async_db)
):
    """Загрузить аватар"""

    # Проверяем формат
    allowed_formats = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
    file_ext = os.path.splitext(file.filename)[1].lower()

    if file_ext not in allowed_formats:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Недопустимый формат. Разрешены: {', '.join(allowed_formats)}"
        )

    # Проверяем размер (5 MB)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Файл слишком большой (максимум 5 МБ)"
        )

    # Сохраняем файл
    import uuid
    filename = f"avatar_{current_user.id}_{uuid.uuid4()}{file_ext}"
    avatar_dir = "uploads/avatars"
    os.makedirs(avatar_dir, exist_ok=True)

    file_path = os.path.join(avatar_dir, filename)
    with open(file_path, 'wb') as f:
        f.write(contents)

    # Обновляем URL
    current_user.avatar_url = f"/uploads/avatars/{filename}"
    await db.commit()

    return {
        "message": "Аватар загружен",
        "avatar_url": current_user.avatar_url
    }


@router.get("/me/stats", response_model=UserStats)
@cache_result("user_stats", ttl=300)
async def get_my_stats(
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_async_db)
):
    """Получить детальную статистику"""

    # Общее количество сдач
    total_submissions = await db.scalar(
        select(func.count(Submission.id)).where(
            Submission.user_id == current_user.id
        )
    )

    # Успешные сдачи (score >= 50)
    successful = await db.scalar(
        select(func.count(Submission.id)).where(
            and_(
                Submission.user_id == current_user.id,
                Submission.score >= 50
            )
        )
    )

    # Статистика за неделю
    week_ago = datetime.utcnow() - timedelta(days=7)
    week_submissions = await db.scalar(
        select(func.count(Submission.id)).where(
            and_(
                Submission.user_id == current_user.id,
                Submission.submitted_at >= week_ago
            )
        )
    )

    # Заработанные монеты
    earned_result = await db.execute(
        select(func.sum(Transaction.coins_amount)).where(
            and_(
                Transaction.user_id == current_user.id,
                Transaction.coins_amount > 0
            )
        )
    )
    total_earned = earned_result.scalar() or 0

    # Количество достижений
    achievements_count = await db.scalar(
        select(func.count()).select_from(
            select(1).join_from(
                User,
                User.achievements
            ).where(User.id == current_user.id).subquery()
        )
    )

    # Позиция в рейтинге
    rank_query = await db.execute(
        select(func.count(User.id)).where(
            or_(
                User.level > current_user.level,
                and_(
                    User.level == current_user.level,
                    User.experience > current_user.experience
                )
            )
        )
    )
    rank = rank_query.scalar() + 1

    return UserStats(
        user_id=current_user.id,
        total_submissions=total_submissions or 0,
        successful_submissions=successful or 0,
        success_rate=round((successful / total_submissions * 100) if total_submissions > 0 else 0, 1),
        week_submissions=week_submissions or 0,
        total_coins_earned=int(total_earned),
        achievements_unlocked=achievements_count or 0,
        current_streak=current_user.streak_days,
        best_score=current_user.best_score,
        total_time_spent=current_user.total_time_spent,
        rank_position=rank
    )


@router.get("/me/transactions", response_model=List[TransactionResponse])
async def get_my_transactions(
        skip: int = 0,
        limit: int = 50,
        current_user: User = Depends(get_current_active_user),
        db: AsyncSession = Depends(get_async_db)
):
    """История транзакций"""

    result = await db.execute(
        select(Transaction)
        .where(Transaction.user_id == current_user.id)
        .order_by(Transaction.created_at.desc())
        .offset(skip)
        .limit(limit)
    )

    transactions = result.scalars().all()
    return transactions


@router.get("/{user_id}", response_model=UserResponse)
@cache_result("user_profile", ttl=600)
async def get_user_by_id(
        user_id: int,
        db: AsyncSession = Depends(get_async_db)
):
    """Получить публичный профиль пользователя"""

    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    return user


@router.get("/", response_model=List[UserResponse])
async def list_users(
        skip: int = 0,
        limit: int = 50,
        role: Optional[UserRole] = None,
        search: Optional[str] = None,
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Получить список пользователей (только для админов)"""

    query = select(User)

    # Фильтры
    if role:
        query = query.where(User.role == role)

    if search:
        query = query.where(
            or_(
                User.username.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%"),
                User.full_name.ilike(f"%{search}%")
            )
        )

    query = query.offset(skip).limit(limit)

    result = await db.execute(query)
    users = result.scalars().all()

    return users


@router.put("/{user_id}/role")
async def update_user_role(
        user_id: int,
        new_role: UserRole,
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Изменить роль пользователя (только для админов)"""

    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    user.role = new_role
    await db.commit()

    return {"message": f"Роль пользователя изменена на {new_role.value}"}


@router.post("/{user_id}/ban")
async def ban_user(
        user_id: int,
        reason: str,
        duration_days: int = 7,
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Заблокировать пользователя"""

    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    user.is_active = False
    user.locked_until = datetime.utcnow() + timedelta(days=duration_days)

    await db.commit()

    return {
        "message": f"Пользователь заблокирован на {duration_days} дней",
        "reason": reason,
        "locked_until": user.locked_until
    }


@router.post("/{user_id}/unban")
async def unban_user(
        user_id: int,
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Разблокировать пользователя"""

    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    user.is_active = True
    user.locked_until = None
    user.failed_login_attempts = 0

    await db.commit()

    return {"message": "Пользователь разблокирован"}


@router.delete("/{user_id}")
async def delete_user(
        user_id: int,
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Удалить пользователя (soft delete)"""

    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    # Soft delete
    user.is_active = False
    user.deleted_at = datetime.utcnow()

    await db.commit()

    return {"message": "Пользователь удален"}