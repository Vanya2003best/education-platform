from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_async_db
from app.models import User, UserRole
from app.schemas import UserCreate, UserResponse, Token
from app.auth import AuthService, get_current_user
from app.config import settings

router = APIRouter()

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_async_db)):
    # проверка username
    if (await db.execute(select(User).where(User.username == user_data.username))).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Пользователь с таким именем уже существует")

    # проверка email
    if (await db.execute(select(User).where(User.email == user_data.email))).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email уже зарегистрирован")

    # сложность пароля
    is_valid, msg = AuthService.validate_password_strength(user_data.password)
    if not is_valid:
        raise HTTPException(status_code=400, detail=msg)

    # создание пользователя
    new_user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=AuthService.get_password_hash(user_data.password),
        full_name=user_data.full_name,
        role=UserRole.STUDENT,
        coins=settings.INITIAL_COINS,
        level=1,
        experience=0,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    # важно: возвращаем ORM-объект, Pydantic берёт поля через from_attributes
    return new_user

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(),
                db: AsyncSession = Depends(get_async_db)):
    # аутентификация
    user = await AuthService.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Неправильное имя пользователя или пароль",
                            headers={"WWW-Authenticate": "Bearer"})
    # выдаём токены
    return AuthService.create_tokens(user.id, user.role.value)

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/refresh")
async def refresh_token(refresh_token: str, db: AsyncSession = Depends(get_async_db)):
    """Обновить access-токен по refresh"""
    payload = await AuthService.decode_token(refresh_token)
    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("sub")
    role = payload.get("role")
    if not user_id or not role:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    new_access = AuthService.create_token({"sub": user_id, "role": role}, "access")
    return {"access_token": new_access, "token_type": "bearer"}


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user)):
    """Выход (место для blacklist refresh/acc токена)"""
    return {"message": "Successfully logged out"}


@router.get("/profile/{user_id}", response_model=UserResponse)
async def get_user_profile(user_id: int, db: AsyncSession = Depends(get_async_db)):
    """Публичный профиль пользователя"""
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return UserResponse.model_validate(user, from_attributes=True)
