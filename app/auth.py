"""
Улучшенная аутентификация с refresh токенами и 2FA
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer, HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import pyotp
import qrcode
import io
import base64
import secrets
import re
import logging

from app.config import settings
from app.database import get_async_db
from app.models import User, UserRole
from app.utils.cache import cache_manager

import bcrypt
from passlib.hash import pbkdf2_sha256

logger = logging.getLogger(__name__)


def _get_bcrypt_rounds() -> int:
    """Безопасно получить количество раундов для bcrypt."""
    rounds = getattr(settings, "BCRYPT_ROUNDS", 12)
    # Значение должно находиться в допустимом диапазоне bcrypt (4-31)
    return max(4, min(int(rounds), 31))

# OAuth2 схемы
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")
bearer_scheme = HTTPBearer()


class AuthService:
    """Сервис аутентификации"""

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Проверка пароля"""
        try:
            if not hashed_password:
                return False

            hashed_password = hashed_password.strip()
            normalized = hashed_password.lstrip("$")

            if normalized.startswith("pbkdf2_sha256$") or normalized.startswith("pbkdf2-sha256$"):
                return pbkdf2_sha256.verify(plain_password, hashed_password)

            return bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8")
            )
        except ValueError as exc:
            # Некорректный хеш (например, поврежден или устаревший формат)
            logger.warning("Password verify failed: %s", exc)
            return False
        except Exception:
            logger.exception("Password verify backend error")
            raise HTTPException(status_code=500, detail="Password verify backend error")

    @staticmethod
    def get_password_hash(password: str) -> str:
        """Хеширование пароля"""
        try:
            rounds = _get_bcrypt_rounds()
            salt = bcrypt.gensalt(rounds=rounds)
            hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
            return hashed.decode("utf-8")
        except ValueError as exc:
            logger.warning("Password hashing failed: %s", exc)
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception:
            logger.exception("Password hash backend error")
            raise HTTPException(status_code=500, detail="Password hash backend error")

    @staticmethod
    def validate_password_strength(password: str) -> tuple[bool, str]:
        """
        Проверка сложности пароля
        Returns: (is_valid, error_message)
        """
        if len(password) < settings.PASSWORD_MIN_LENGTH:
            return False, f"Пароль должен быть минимум {settings.PASSWORD_MIN_LENGTH} символов"

        if settings.PASSWORD_REQUIRE_UPPERCASE and not re.search(r'[A-Z]', password):
            return False, "Пароль должен содержать хотя бы одну заглавную букву"

        if settings.PASSWORD_REQUIRE_NUMBER and not re.search(r'\d', password):
            return False, "Пароль должен содержать хотя бы одну цифру"

        # Проверка на распространенные пароли
        common_passwords = ['password', '12345678', 'qwerty', 'abc123']
        if password.lower() in common_passwords:
            return False, "Пароль слишком простой"

        return True, ""

    @staticmethod
    def create_token(data: Dict[str, Any], token_type: str = "access") -> str:
        """Создание JWT токена"""
        to_encode = data.copy()

        if token_type == "access":
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        elif token_type == "refresh":
            expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
        else:
            raise ValueError(f"Unknown token type: {token_type}")

        to_encode.update({
            "exp": expire,
            "type": token_type,
            "jti": secrets.token_urlsafe(16)  # JWT ID для отзыва токенов
        })

        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    @staticmethod
    def create_tokens(user_id: int, role: UserRole | str) -> Dict[str, str]:
        """Создание пары access и refresh токенов"""
        role_value = role.value if isinstance(role, UserRole) else str(role)
        data = {"sub": str(user_id), "role": role_value}

        return {
            "access_token": AuthService.create_token(data, "access"),
            "refresh_token": AuthService.create_token(data, "refresh"),
            "token_type": "bearer"
        }

    @staticmethod
    async def decode_token(token: str) -> Dict[str, Any]:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

            jti = payload.get("jti")
            # ✅ проверяем подключение к Redis и оборачиваем в try
            if jti and getattr(cache_manager, "is_connected", lambda: False)():
                try:
                    if await cache_manager.is_token_blacklisted(jti):
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Token has been revoked"
                        )
                except Exception:
                    # Если Redis сбо́ит — НЕ роняем авторизацию
                    pass

            return payload

        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Could not validate credentials: {str(e)}"
            )

    @staticmethod
    async def authenticate_user(
        db: AsyncSession,
        username: str,
        password: str
    ) -> Optional[User]:
        """Аутентификация пользователя"""
        # Ищем пользователя
        result = await db.execute(
            select(User).where(
                (User.username == username) | (User.email == username)
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            return None

        # Проверяем, не заблокирован ли аккаунт
        if user.locked_until and user.locked_until > datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Account locked until {user.locked_until}"
            )

        # Проверяем пароль
        if not AuthService.verify_password(password, user.password_hash):
            # Увеличиваем счетчик неудачных попыток
            user.failed_login_attempts += 1

            # Блокируем после 5 попыток
            if user.failed_login_attempts >= 5:
                user.locked_until = datetime.utcnow() + timedelta(minutes=30)
                await db.commit()
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail="Too many failed attempts. Account locked for 30 minutes"
                )

            await db.commit()
            return None

        # Сбрасываем счетчик при успешном входе
        user.failed_login_attempts = 0
        user.last_login = datetime.utcnow()
        await db.commit()

        return user

    @staticmethod
    def generate_2fa_secret() -> str:
        """Генерация секрета для 2FA"""
        return pyotp.random_base32()

    @staticmethod
    def generate_2fa_qr_code(user_email: str, secret: str) -> str:
        """Генерация QR кода для 2FA"""
        totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
            name=user_email,
            issuer_name=settings.APP_NAME
        )

        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(totp_uri)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format='PNG')

        return base64.b64encode(buf.getvalue()).decode()

    @staticmethod
    def verify_2fa_token(secret: str, token: str) -> bool:
        """Проверка 2FA токена"""
        totp = pyotp.TOTP(secret)
        return totp.verify(token, valid_window=1)


# Зависимости для endpoints
async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_async_db)
) -> User:
    """Получить текущего пользователя из JWT токена"""

    token = credentials.credentials

    # Декодируем токен
    payload = await AuthService.decode_token(token)

    # Проверяем тип токена
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type"
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )

    # Получаем пользователя из БД
    result = await db.execute(
        select(User).where(User.id == int(user_id))
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )

    # Обновляем последнюю активность
    user.last_activity = datetime.utcnow()
    await db.commit()

    # Сохраняем пользователя в request state для логирования
    request.state.user = user

    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """Проверка, что пользователь активен и верифицирован"""
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Please verify your email first"
        )
    return current_user


class RoleChecker:
    """Проверка ролей пользователя"""

    def __init__(self, allowed_roles: list[UserRole]):
        self.allowed_roles = allowed_roles

    def __call__(self, user: User = Depends(get_current_active_user)) -> User:
        if user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions"
            )
        return user


# Shortcuts для проверки ролей
require_teacher = RoleChecker([UserRole.TEACHER, UserRole.ADMIN])
require_admin = RoleChecker([UserRole.ADMIN])
require_student = RoleChecker([UserRole.STUDENT])


class RateLimiter:
    """Rate limiting для защиты от брутфорса"""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # ✅ простой in-memory фолбэк: {key: [timestamps]}
        self._mem: dict[str, list[float]] = {}

    async def __call__(self, request: Request) -> None:
        client_id = request.client.host if request.client else "unknown"
        key = f"rate_limit:{client_id}"
        now = datetime.utcnow().timestamp()
        window_start = now - self.window_seconds

        try:
            # ✅ используем Redis, только если он реально подключен
            if getattr(cache_manager, "is_connected", lambda: False)():
                # предполагаем сигнатуру increment(key, ttl)
                count = await cache_manager.increment(key, ttl=self.window_seconds)
            else:
                # ✅ in-memory
                times = self._mem.get(key, [])
                times = [t for t in times if t > window_start]
                times.append(now)
                self._mem[key] = times
                count = len(times)
        except Exception:
            # ✅ при любой ошибке лимитер не должен ронять эндпойнт
            return

        if count > self.max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests"
            )


# Rate limiters для разных endpoints
auth_rate_limiter = RateLimiter(max_requests=5, window_seconds=60)
api_rate_limiter = RateLimiter(max_requests=100, window_seconds=60)