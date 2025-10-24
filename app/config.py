"""
Конфигурация приложения с валидацией и безопасностью
"""
from pydantic_settings import BaseSettings
from typing import Optional, List
from functools import lru_cache
import secrets


class Settings(BaseSettings):
    """Настройки приложения из переменных окружения"""

    # Database
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/education_db"
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 40
    DATABASE_POOL_TIMEOUT: int = 30

    # Redis
    REDIS_URL: Optional[str] = "redis://localhost:6379/0"
    REDIS_TTL: int = 3600  # 1 час

    # Security
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 часа
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_REQUIRE_UPPERCASE: bool = True
    PASSWORD_REQUIRE_NUMBER: bool = True

    # Rate Limiting
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_PERIOD: int = 60  # секунды

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:8000"]
    CORS_ALLOW_CREDENTIALS: bool = True

    # OpenAI (для AI проверки)
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_MAX_RETRIES: int = 3
    OPENAI_TIMEOUT: int = 30

    # File Upload
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10 MB
    ALLOWED_EXTENSIONS: List[str] = [".jpg", ".jpeg", ".png", ".heic", ".webp"]
    UPLOAD_DIR: str = "uploads/submissions"

    # S3 Storage (опционально)
    S3_BUCKET_NAME: Optional[str] = None
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_REGION: str = "us-east-1"

    # Application
    APP_NAME: str = "Education Platform"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"  # development, staging, production

    # Email
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAIL_FROM: str = "noreply@education-platform.com"

    # Monitoring
    SENTRY_DSN: Optional[str] = None
    PROMETHEUS_ENABLED: bool = True

    # Gamification
    INITIAL_COINS: int = 100
    LEVEL_UP_BONUS: int = 50
    MAX_LEVEL: int = 100

    # AI Checking
    OCR_LANGUAGE: str = "rus+eng"
    OCR_TIMEOUT: int = 30
    AI_CHECK_TIMEOUT: int = 60
    AI_TEMPERATURE: float = 0.3

    # Celery
    CELERY_BROKER_URL: Optional[str] = None
    CELERY_RESULT_BACKEND: Optional[str] = None
    CELERY_TASK_TIME_LIMIT: int = 300  # 5 минут

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json или text
    LOG_FILE: Optional[str] = "logs/app.log"

    # Features flags
    FEATURE_AI_CHECKING: bool = True
    FEATURE_EMAIL_NOTIFICATIONS: bool = False
    FEATURE_SOCIAL_LOGIN: bool = False
    FEATURE_ACHIEVEMENTS: bool = True
    FEATURE_LEADERBOARD: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = True

    @property
    def database_url_async(self) -> str:
        """URL для async драйвера PostgreSQL"""
        if self.DATABASE_URL.startswith("postgresql://"):
            return self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
        return self.DATABASE_URL

    @property
    def is_production(self) -> bool:
        """Проверка production окружения"""
        return self.ENVIRONMENT == "production"

    @property
    def is_development(self) -> bool:
        """Проверка development окружения"""
        return self.ENVIRONMENT == "development"


@lru_cache()
def get_settings() -> Settings:
    """Получить настройки (кэшированные)"""
    return Settings()


settings = get_settings()