"""
Конфигурация приложения
"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Настройки приложения из переменных окружения"""

    # Database
    DATABASE_URL: str = "postgresql://user:password@localhost:5432/education_db"

    # Security
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 часа

    # OpenAI (для AI проверки)
    OPENAI_API_KEY: Optional[str] = None

    # File Upload
    MAX_UPLOAD_SIZE: int = 10 * 1024 * 1024  # 10 MB

    # Application
    DEBUG: bool = False
    APP_NAME: str = "Education Platform"

    # Redis (для фоновых задач) - опционально
    REDIS_URL: Optional[str] = None

    # Cloudinary (для хранения изображений) - опционально
    CLOUDINARY_CLOUD_NAME: Optional[str] = None
    CLOUDINARY_API_KEY: Optional[str] = None
    CLOUDINARY_API_SECRET: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()