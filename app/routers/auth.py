# app/routers/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import get_async_db
from app.models import User, UserRole
from app.schemas import UserCreate, UserResponse, Token
from app.auth import AuthService, get_current_user
from app.config import settings
import logging

router = APIRouter()
log = logging.getLogger(__name__)

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user_data: UserCreate, db: AsyncSession = Depends(get_async_db)):
    try:
        # уникальность
        if (await db.execute(select(User).where(User.username == user_data.username))).scalar_one_or_none():
            raise HTTPException(400, "Пользователь с таким именем уже существует")
        if (await db.execute(select(User).where(User.email == user_data.email))).scalar_one_or_none():
            raise HTTPException(400, "Email уже зарегистрирован")

        ok, msg = AuthService.validate_password_strength(user_data.password)
        if not ok:
            raise HTTPException(400, msg)

        user = User(
            username=user_data.username,
            email=user_data.email,
            password_hash=AuthService.get_password_hash(user_data.password),
            full_name=user_data.full_name,
            role=UserRole.STUDENT,
            coins=settings.INITIAL_COINS,
            level=1,
            experience=0,
            failed_login_attempts=0,
            is_active=True,
            is_verified=False,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    except IntegrityError:
        await db.rollback()
        raise HTTPException(409, "Пользователь с таким email или логином уже существует")
    except HTTPException:
        raise
    except Exception:
        log.exception("register failed")
        raise HTTPException(500, "Register failed")

@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(),
                db: AsyncSession = Depends(get_async_db)):
    try:
        user = await AuthService.authenticate_user(db, form_data.username, form_data.password)
        if not user:
            raise HTTPException(status_code=401, detail="Неправильное имя пользователя или пароль",
                                headers={"WWW-Authenticate": "Bearer"})
        return AuthService.create_tokens(user.id, user.role)
    except HTTPException:
        raise
    except Exception:
        log.exception("login failed")
        raise HTTPException(500, "Login failed")


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Возвращает текущего авторизованного пользователя."""
    return current_user