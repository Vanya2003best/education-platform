"""
API для регистрации и входа
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import timedelta

from app.database import get_async_db
from app.models import User, UserRole
from app.schemas import UserCreate, UserResponse, Token
from app.auth import (
    AuthService,  # ИСПРАВЛЕНО: импортируем класс
    get_current_user,
    auth_rate_limiter
)
from app.config import settings

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_async_db)
):
    """Регистрация нового пользователя"""

    # Проверяем, не существует ли уже такой username
    from sqlalchemy import select

    existing_user = await db.execute(
        select(User).where(User.username == user_data.username)
    )
    if existing_user.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Пользователь с таким именем уже существует"
        )

    # Проверяем email
    existing_email = await db.execute(
        select(User).where(User.email == user_data.email)
    )
    if existing_email.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail="Email уже зарегистрирован"
        )

    # Валидируем пароль
    is_valid, error_msg = AuthService.validate_password_strength(user_data.password)
    if not is_valid:
        raise HTTPException(
            status_code=400,
            detail=error_msg
        )

    # Создаем нового пользователя
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=AuthService.get_password_hash(user_data.password),  # ИСПРАВЛЕНО
        full_name=user_data.full_name,
        role=UserRole.STUDENT,
        coins=settings.INITIAL_COINS,
        level=1,
        experience=0
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return new_user


@router.post("/login", response_model=Token, dependencies=[Depends(auth_rate_limiter)])
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_async_db)
):
    """Вход в систему (получение JWT токена)"""

    # Аутентификация
    user = await AuthService.authenticate_user(db, form_data.username, form_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неправильное имя пользователя или пароль",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Создаем токены
    tokens = AuthService.create_tokens(user.id, user.role.value)

    return tokens


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Получить информацию о текущем пользователе"""
    return current_user


@router.post("/refresh")
async def refresh_token(
    refresh_token: str,
    db: AsyncSession = Depends(get_async_db)
):
    """Обновить access токен используя refresh токен"""

    # Декодируем refresh токен
    payload = await AuthService.decode_token(refresh_token)

    # Проверяем тип токена
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type"
        )

    user_id = payload.get("sub")
    role = payload.get("role")

    if not user_id or not role:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )

    # Создаем новый access токен
    new_access_token = AuthService.create_token(
        {"sub": user_id, "role": role},
        "access"
    )

    return {
        "access_token": new_access_token,
        "token_type": "bearer"
    }


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """Выйти из системы (в будущем - добавить токен в blacklist)"""

    # TODO: Добавить токен в blacklist в Redis

    return {"message": "Successfully logged out"}


@router.get("/profile/{user_id}", response_model=UserResponse)
async def get_user_profile(
    user_id: int,
    db: AsyncSession = Depends(get_async_db)
):
    """Получить публичный профиль пользователя"""

    from sqlalchemy import select

    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    return user