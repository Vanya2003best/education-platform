"""
Улучшенная аутентификация с refresh токенами и 2FA
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status, Request
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
import hashlib
import hmac
import binascii

from app.config import settings
from app.database import get_async_db
from app.models import User, UserRole
from app.utils.cache import cache_manager

try:  # pragma: no cover - optional dependency
    import bcrypt  # type: ignore
except ImportError:  # pragma: no cover - handled at runtime
    bcrypt = None  # type: ignore

try:  # pragma: no cover - optional dependency
    from passlib.hash import pbkdf2_sha256
except ImportError:  # pragma: no cover - handled at runtime
    pbkdf2_sha256 = None  # type: ignore

try:  # pragma: no cover - optional dependency
    from passlib.hash import bcrypt as passlib_bcrypt
except ImportError:  # pragma: no cover - handled at runtime
    passlib_bcrypt = None  # type: ignore

logger = logging.getLogger(__name__)

# OAuth2 схемы


def _get_bcrypt_rounds() -> int:
    """Безопасно получить количество раундов для bcrypt."""
    rounds = getattr(settings, "BCRYPT_ROUNDS", 12)
    return max(4, min(int(rounds), 31))


def _urlsafe_b64encode_no_padding(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _urlsafe_b64decode_no_padding(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def _hash_with_native_pbkdf2(password: str) -> str:
    """Нативный PBKDF2-хеш, если нет passlib."""
    try:
        rounds = max(1, int(getattr(settings, "PBKDF2_ROUNDS", 600_000)))
    except (TypeError, ValueError):  # defensive
        rounds = 600_000

    try:
        salt = secrets.token_bytes(16)
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            rounds,
        )
        salt_b64 = _urlsafe_b64encode_no_padding(salt)
        hash_b64 = _urlsafe_b64encode_no_padding(derived)
        return f"$pbkdf2-sha256$native${rounds}${salt_b64}${hash_b64}"
    except Exception as exc:  # крайне редко
        logger.exception("Native PBKDF2 hashing failed")
        raise HTTPException(status_code=500, detail="Password hash backend error") from exc


def _hash_with_pbkdf2(password: str) -> str:
    """PBKDF2 через passlib с fallback на нативный."""
    if pbkdf2_sha256 is None:
        logger.warning("passlib pbkdf2 backend unavailable, using native PBKDF2")
        return _hash_with_native_pbkdf2(password)

    hash_fn = getattr(pbkdf2_sha256, "hash", None)
    if not callable(hash_fn):
        logger.warning("passlib pbkdf2 hash helper missing, using native PBKDF2 fallback")
        return _hash_with_native_pbkdf2(password)

    try:
        return hash_fn(password)
    except Exception:
        logger.exception("Passlib PBKDF2 hashing failed, using native fallback")
        return _hash_with_native_pbkdf2(password)


def _verify_native_pbkdf2(plain_password: str, hashed_password: str) -> bool:
    """Проверка для хеша вида $pbkdf2-sha256$native$..."""
    parts = hashed_password.split("$")
    if len(parts) != 6:
        return False

    try:
        _, algorithm, marker, rounds_str, salt_b64, hash_b64 = parts
        if algorithm.lower() != "pbkdf2-sha256" or marker.lower() != "native":
            return False
        rounds = int(rounds_str)
        salt = _urlsafe_b64decode_no_padding(salt_b64)
        stored = _urlsafe_b64decode_no_padding(hash_b64)
    except (ValueError, binascii.Error):
        return False
    except Exception:
        return False

    derived = hashlib.pbkdf2_hmac(
        "sha256",
        plain_password.encode("utf-8"),
        salt,
        rounds,
    )
    return hmac.compare_digest(derived, stored)
def _try_base64_decode(value: str) -> list[bytes]:
    """Попытаться декодировать строку как base64/urlsafe-base64."""
    candidates: list[bytes] = []
    if not value:
        return candidates

    padded = value + "=" * (-len(value) % 4)
    for decoder in (base64.b64decode, base64.urlsafe_b64decode):
        try:
            decoded = decoder(padded.encode("ascii"))
        except (ValueError, binascii.Error):
            continue
        if decoded and decoded not in candidates:
            candidates.append(decoded)
    return candidates


def _verify_werkzeug_pbkdf2(plain_password: str, hashed_password: str) -> bool:
    """Проверка хеша формата pbkdf2:sha256:<rounds>$<salt>$<hash>."""
    parts = hashed_password.split("$")
    if len(parts) != 3:
        return False

    algo_part, salt, stored_hash = parts
    try:
        prefix, hash_name, rounds_str = algo_part.split(":", 2)
    except ValueError:
        return False

    if prefix != "pbkdf2" or hash_name != "sha256":
        return False

    try:
        rounds = int(rounds_str)
    except ValueError:
        return False

    salt = salt.strip()
    stored_hash = stored_hash.strip()
    if not salt or not stored_hash:
        return False

    plain_bytes = plain_password.encode("utf-8")

    def compare_candidate(derived: bytes) -> bool:
        candidate_b64 = base64.b64encode(derived).decode("utf-8").strip()
        if hmac.compare_digest(candidate_b64, stored_hash):
            return True
        if hmac.compare_digest(candidate_b64.rstrip("="), stored_hash.rstrip("=")):
            return True
        candidate_hex = binascii.hexlify(derived).decode("ascii")
        if hmac.compare_digest(candidate_hex, stored_hash.lower()):
            return True
        return False

    salt_variants = [salt.encode("utf-8")]
    salt_variants.extend(_try_base64_decode(salt))

    checked: set[bytes] = set()
    for salt_bytes in salt_variants:
        if not salt_bytes or salt_bytes in checked:
            continue
        checked.add(salt_bytes)
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            plain_bytes,
            salt_bytes,
            rounds,
        )
        if compare_candidate(derived):
            return True

    return False

class AuthService:
    """Сервис аутентификации"""

    # ---------- ПАРОЛИ ----------

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Проверка пароля с учётом разных форматов хеша."""
        try:
            if not hashed_password:
                return False

            # Страхуемся от неожиданных типов данных из БД
            if isinstance(plain_password, (bytes, bytearray, memoryview)):
                plain_password = bytes(plain_password).decode("utf-8", "ignore")
            else:
                plain_password = str(plain_password)

            if isinstance(hashed_password, (bytes, bytearray, memoryview)):
                hashed_password = bytes(hashed_password).decode("utf-8", "ignore")
            else:
                hashed_password = str(hashed_password)

            hashed_password = hashed_password.strip()
            normalized = hashed_password.lstrip("$")
            normalized_lower = normalized.lower()

            # 1) наш собственный нативный формат: $pbkdf2-sha256$native$...
            if normalized_lower.startswith("pbkdf2-sha256$native$"):
                return _verify_native_pbkdf2(plain_password, hashed_password)

            # 2) обычные pbkdf2 из passlib
            if (
                normalized_lower.startswith("pbkdf2_sha256$")
                or normalized_lower.startswith("pbkdf2-sha256$")
                or normalized_lower.startswith("pbkdf2$")
            ):
                if pbkdf2_sha256 is None:
                    logger.warning("passlib pbkdf2 backend unavailable, attempting native verify")
                    return _verify_native_pbkdf2(plain_password, hashed_password)
                try:
                    return pbkdf2_sha256.verify(plain_password, hashed_password)
                except Exception:
                    logger.exception("Passlib PBKDF2 verify failed, attempting native verifier")
                    return _verify_native_pbkdf2(plain_password, hashed_password)
            # 2.1) формат werkzeug: pbkdf2:sha256:<rounds>$<salt>$<hash>
            if normalized_lower.startswith("pbkdf2:sha256:"):
                return _verify_werkzeug_pbkdf2(plain_password, hashed_password)
            # 3) bcrypt
            if normalized.startswith(("2a$", "2b$", "2y$")):
                if bcrypt is not None:
                    return bcrypt.checkpw(
                        plain_password.encode("utf-8"),
                        hashed_password.encode("utf-8")
                    )
                if passlib_bcrypt is not None:
                    try:
                        return passlib_bcrypt.verify(plain_password, hashed_password)
                    except Exception as exc:
                        logger.warning("Passlib bcrypt verify fallback failed: %s", exc)
                        return False

            # 4) если это что-то ещё и нет bcrypt — отказываем
            if bcrypt is None:
                logger.warning(
                    "bcrypt backend unavailable and hash format not supported: %s",
                    hashed_password[:12]
                )
                return False

            # 5) дефолт: пробуем bcrypt
            return bcrypt.checkpw(
                plain_password.encode("utf-8"),
                hashed_password.encode("utf-8")
            )


        except (TypeError, ValueError) as exc:
            logger.warning("Password verify failed: %s", exc)
            return False
        except Exception:
            logger.exception("Password verify backend error")
            raise HTTPException(status_code=500, detail="Password verify backend error")

    @staticmethod
    def get_password_hash(password: str) -> str:
        """Хеширование пароля с нормальным fallback."""
        # если нет bcrypt вовсе — сразу PBKDF2 с запасом
        if bcrypt is None:
            logger.warning("bcrypt backend unavailable, falling back to PBKDF2 hashing")
            return _hash_with_pbkdf2(password)

        try:
            rounds = _get_bcrypt_rounds()
            salt = bcrypt.gensalt(rounds=rounds)
            hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
            return hashed.decode("utf-8")
        except ValueError as exc:
            logger.warning("Password hashing failed: %s", exc)
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception:
            logger.exception("Password hash backend error, using PBKDF2 fallback")
            return _hash_with_pbkdf2(password)

    @staticmethod
    def validate_password_strength(password: str) -> tuple[bool, str]:
        """Проверка сложности пароля."""
        if len(password) < settings.PASSWORD_MIN_LENGTH:
            return False, f"Пароль должен быть минимум {settings.PASSWORD_MIN_LENGTH} символов"
        if settings.PASSWORD_REQUIRE_UPPERCASE and not re.search(r'[A-Z]', password):
            return False, "Пароль должен содержать хотя бы одну заглавную букву"
        if settings.PASSWORD_REQUIRE_NUMBER and not re.search(r'\d', password):
            return False, "Пароль должен содержать хотя бы одну цифру"
        if password.lower() in ['password', '12345678', 'qwerty', 'abc123']:
            return False, "Пароль слишком простой"
        return True, ""

    # ---------- JWT ----------

    @staticmethod
    def create_token(data: Dict[str, Any], token_type: str = "access") -> str:
        """Создание JWT токена."""
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
            "jti": secrets.token_urlsafe(16)
        })

        return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    @staticmethod
    def create_tokens(user_id: int, role: UserRole | str) -> Dict[str, str]:
        """Создание пары access + refresh."""
        role_value = role.value if isinstance(role, UserRole) else str(role)
        data = {"sub": str(user_id), "role": role_value}

        return {
            "access_token": AuthService.create_token(data, "access"),
            "refresh_token": AuthService.create_token(data, "refresh"),
            "token_type": "bearer"
        }

    @staticmethod
    async def decode_token(token: str) -> Dict[str, Any]:
        """Декодирование JWT и проверка blacklist в Redis."""
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

            jti = payload.get("jti")
            if jti and getattr(cache_manager, "is_connected", lambda: False)():
                try:
                    if await cache_manager.is_token_blacklisted(jti):
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Token has been revoked"
                        )
                except Exception:
                    # не роняем авторизацию, если Redis лагает
                    pass

            return payload

        except JWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Could not validate credentials: {str(e)}"
            )

    # ---------- Пользователь ----------

    @staticmethod
    async def authenticate_user(
        db: AsyncSession,
        username: str,
        password: str
    ) -> Optional[User]:
        """Аутентификация пользователя по логину/почте и паролю."""
        result = await db.execute(
            select(User).where(
                (User.username == username) | (User.email == username)
            )
        )
        user = result.scalar_one_or_none()

        if not user:
            return None

        # заблокирован?
        if user.locked_until and user.locked_until > datetime.utcnow():
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Account locked until {user.locked_until}"
            )

        # проверяем пароль
        if not AuthService.verify_password(password, user.password_hash):
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                user.locked_until = datetime.utcnow() + timedelta(minutes=30)
                await db.commit()
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail="Too many failed attempts. Account locked for 30 minutes"
                )
            await db.commit()
            return None

        # успех — сбрасываем счётчик
        user.failed_login_attempts = 0
        user.last_login = datetime.utcnow()
        await db.commit()
        return user

    # ---------- 2FA ----------

    @staticmethod
    def generate_2fa_secret() -> str:
        return pyotp.random_base32()

    @staticmethod
    def generate_2fa_qr_code(user_email: str, secret: str) -> str:
        totp_uri = pyotp.TOTP(secret).provisioning_uri(
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
        totp = pyotp.TOTP(secret)
        return totp.verify(token, valid_window=1)


# --------- Зависимости для эндпоинтов ---------

async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
) -> User:
    auth_header = request.headers.get("Authorization", "")
    scheme, _, token = auth_header.partition(" ")

    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing bearer token",
        )
    payload = await AuthService.decode_token(token)

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    result = await db.execute(select(User).where(User.id == int(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Inactive user")

    user.last_activity = datetime.utcnow()
    await db.commit()

    request.state.user = user
    return user


async def get_current_active_user(
    current_user: User = Depends(get_current_user)
) -> User:
    if not current_user.is_verified:
        raise HTTPException(
            status_code=403,
            detail="Please verify your email first"
        )
    return current_user


class RoleChecker:
    def __init__(self, allowed_roles: list[UserRole]):
        self.allowed_roles = allowed_roles

    def __call__(self, user: User = Depends(get_current_active_user)) -> User:
        if user.role not in self.allowed_roles:
            raise HTTPException(status_code=403, detail="Not enough permissions")
        return user

async def get_admin_user(current_user: User = Depends(get_current_active_user)) -> User:
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admins only",
        )
    return current_user


require_teacher = RoleChecker([UserRole.TEACHER, UserRole.ADMIN])
require_admin = get_admin_user
require_student = RoleChecker([UserRole.STUDENT])


class RateLimiter:
    """Простой rate-limiter с Redis + in-memory fallback."""

    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._mem: dict[str, list[float]] = {}

    async def __call__(self, request: Request) -> None:
        client_id = request.client.host if request.client else "unknown"
        key = f"rate_limit:{client_id}"
        now = datetime.utcnow().timestamp()
        window_start = now - self.window_seconds

        try:
            if getattr(cache_manager, "is_connected", lambda: False)():
                count = await cache_manager.increment(key, ttl=self.window_seconds)
            else:
                times = self._mem.get(key, [])
                times = [t for t in times if t > window_start]
                times.append(now)
                self._mem[key] = times
                count = len(times)
        except Exception:
            return

        if count > self.max_requests:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests"
            )


auth_rate_limiter = RateLimiter(max_requests=5, window_seconds=60)
api_rate_limiter = RateLimiter(max_requests=100, window_seconds=60)
