"""
Модели базы данных с улучшенной структурой и индексами
"""
from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Text, Boolean,
    Float, JSON, Enum, Index, UniqueConstraint, CheckConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from datetime import datetime
import enum

Base = declarative_base()


class UserRole(enum.Enum):
    """Роли пользователей"""
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"
    PARENT = "parent"


class TaskStatus(enum.Enum):
    """Статусы заданий"""
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class SubmissionStatus(enum.Enum):
    """Статусы проверки работ"""
    PENDING = "pending"
    PROCESSING = "processing"
    CHECKED = "checked"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


class User(Base):
    """Модель пользователя с расширенным функционалом"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100))
    role = Column(Enum(UserRole), default=UserRole.STUDENT, nullable=False, index=True)

    # Профиль
    avatar_url = Column(String(500))
    bio = Column(Text)
    grade = Column(Integer)  # Класс (для учеников)
    school = Column(String(200))
    city = Column(String(100))
    country = Column(String(100))
    timezone = Column(String(50), default="UTC")
    language = Column(String(10), default="ru")

    # Игровые показатели
    coins = Column(Integer, default=0, nullable=False)
    gems = Column(Integer, default=0)  # Премиум валюта
    level = Column(Integer, default=1, nullable=False, index=True)
    experience = Column(Integer, default=0, nullable=False)
    streak_days = Column(Integer, default=0)  # Дней подряд

    # Статистика
    tasks_completed = Column(Integer, default=0, nullable=False)
    tasks_failed = Column(Integer, default=0)
    total_score = Column(Float, default=0.0)
    average_score = Column(Float, default=0.0)
    best_score = Column(Float, default=0.0)
    total_time_spent = Column(Integer, default=0)  # минуты

    # Настройки
    email_notifications = Column(Boolean, default=True)
    push_notifications = Column(Boolean, default=False)
    theme = Column(String(20), default="light")

    # Безопасность
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    is_verified = Column(Boolean, default=False)
    is_premium = Column(Boolean, default=False)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime)
    two_factor_enabled = Column(Boolean, default=False)
    two_factor_secret = Column(String(100))

    # Временные метки
    created_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    last_login = Column(DateTime)
    last_activity = Column(DateTime)
    deleted_at = Column(DateTime)  # Soft delete

    # Связи
    submissions = relationship(
        "Submission",
        back_populates="user",
        foreign_keys="Submission.user_id",  # ДОБАВЛЕНО!
        lazy="dynamic"
    )
    purchases = relationship("Purchase", back_populates="user", lazy="dynamic")
    achievements = relationship("UserAchievement", back_populates="user", lazy="dynamic")
    created_tasks = relationship("Task", back_populates="creator", foreign_keys="Task.created_by")
    transactions = relationship("Transaction", back_populates="user", lazy="dynamic")

    # Индексы
    __table_args__ = (
        Index('idx_user_email_active', 'email', 'is_active'),
        Index('idx_user_role_active', 'role', 'is_active'),
        Index('idx_user_level_exp', 'level', 'experience'),
        CheckConstraint('coins >= 0', name='check_positive_coins'),
        CheckConstraint('level >= 1', name='check_min_level'),
    )

    @validates('email')
    def validate_email(self, key, email):
        """Валидация email"""
        if '@' not in email:
            raise ValueError("Invalid email")
        return email.lower()


class Task(Base):
    """Модель задания с расширенным функционалом"""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)

    # Категоризация
    task_type = Column(String(50), nullable=False, index=True)
    subject = Column(String(50), index=True)
    topic = Column(String(100))  # Подтема
    tags = Column(JSON)  # Теги для поиска

    # Сложность и требования
    difficulty = Column(Integer, default=1, index=True)
    min_level = Column(Integer, default=1)  # Минимальный уровень для доступа
    time_limit = Column(Integer)  # Ограничение времени в минутах
    max_attempts = Column(Integer, default=3)  # Максимум попыток

    # Награды
    reward_coins = Column(Integer, default=10, nullable=False)
    reward_exp = Column(Integer, default=50, nullable=False)
    reward_gems = Column(Integer, default=0)
    bonus_coins = Column(Integer, default=0)  # Бонус за идеальное выполнение

    # Критерии и решения
    checking_criteria = Column(JSON)  # Критерии для AI
    example_solution = Column(Text)
    hints = Column(JSON)  # Подсказки
    resources = Column(JSON)  # Ссылки на материалы

    # Медиа
    image_url = Column(String(500))
    video_url = Column(String(500))
    attachments = Column(JSON)  # Дополнительные файлы

    # Статус и видимость
    status = Column(Enum(TaskStatus), default=TaskStatus.ACTIVE, index=True)
    is_premium = Column(Boolean, default=False)  # Только для премиум
    is_featured = Column(Boolean, default=False)  # Рекомендованное
    order_index = Column(Integer, default=0)  # Порядок отображения

    # Статистика
    submissions_count = Column(Integer, default=0)
    success_rate = Column(Float, default=0.0)
    avg_score = Column(Float, default=0.0)
    avg_completion_time = Column(Float)  # минуты

    # Метаданные
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    published_at = Column(DateTime)
    expires_at = Column(DateTime)  # Для временных заданий

    # Связи
    submissions = relationship("Submission", back_populates="task", lazy="dynamic")
    creator = relationship("User", back_populates="created_tasks", foreign_keys=[created_by])

    # Индексы
    __table_args__ = (
        Index('idx_task_subject_difficulty', 'subject', 'difficulty'),
        Index('idx_task_status_featured', 'status', 'is_featured'),
        Index('idx_task_type_status', 'task_type', 'status'),
    )


class Submission(Base):
    """Модель сдачи работы с расширенными возможностями"""
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False, index=True)

    # Загруженные файлы
    photo_urls = Column(JSON)  # Массив URL для нескольких фото
    photo_filename = Column(String(255))
    file_size = Column(Integer)  # Размер в байтах

    # Контент
    recognized_text = Column(Text)
    user_answer = Column(Text)  # Текстовый ответ (если есть)

    # Результаты проверки
    score = Column(Float, default=0.0, index=True)
    status = Column(Enum(SubmissionStatus), default=SubmissionStatus.PENDING, index=True)

    # AI анализ
    ai_feedback = Column(Text)
    detailed_analysis = Column(JSON)
    confidence_score = Column(Float)  # Уверенность AI в оценке
    plagiarism_score = Column(Float)  # Проверка на плагиат

    # Награды
    coins_earned = Column(Integer, default=0)
    exp_earned = Column(Integer, default=0)
    gems_earned = Column(Integer, default=0)
    achievements_unlocked = Column(JSON)

    # Временные метрики
    submitted_at = Column(DateTime, default=func.now(), index=True)
    started_at = Column(DateTime)  # Когда начал решать
    checked_at = Column(DateTime)
    processing_time = Column(Float)
    completion_time = Column(Integer)  # Время выполнения в минутах

    # Дополнительная информация
    attempt_number = Column(Integer, default=1)
    is_late = Column(Boolean, default=False)
    device_info = Column(JSON)  # Информация об устройстве
    ip_address = Column(String(45))

    # Ручная проверка
    manual_score = Column(Float)
    teacher_feedback = Column(Text)
    reviewed_by = Column(Integer, ForeignKey("users.id"))
    reviewed_at = Column(DateTime)

    # Связи
    user = relationship(
        "User",
        back_populates="submissions",
        foreign_keys=[user_id]
    )
    task = relationship("Task", back_populates="submissions")
    reviewer = relationship(
        "User",
        foreign_keys=[reviewed_by],
        overlaps="submissions"  # ДОБАВЛЕНО!
    )

    # Индексы
    __table_args__ = (
        Index('idx_submission_user_task', 'user_id', 'task_id'),
        Index('idx_submission_status_score', 'status', 'score'),
        Index('idx_submission_submitted_at', 'submitted_at'),
        UniqueConstraint('user_id', 'task_id', 'attempt_number', name='unique_user_task_attempt'),
    )


class Achievement(Base):
    """Модель достижения"""
    __tablename__ = "achievements"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    description = Column(Text)
    icon_url = Column(String(500))

    # Категория и редкость
    category = Column(String(50))  # academic, social, special
    rarity = Column(String(20))  # common, rare, epic, legendary

    # Условия получения
    criteria = Column(JSON)  # Условия в формате JSON
    points = Column(Integer, default=10)

    # Награды
    reward_coins = Column(Integer, default=0)
    reward_gems = Column(Integer, default=0)
    reward_exp = Column(Integer, default=0)

    # Метаданные
    is_hidden = Column(Boolean, default=False)  # Скрытое достижение
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())

    # Связи
    user_achievements = relationship("UserAchievement", back_populates="achievement")


class UserAchievement(Base):
    """Связь пользователь-достижение"""
    __tablename__ = "user_achievements"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    achievement_id = Column(Integer, ForeignKey("achievements.id"), nullable=False)

    unlocked_at = Column(DateTime, default=func.now())
    progress = Column(Integer, default=0)  # Прогресс для составных достижений
    is_claimed = Column(Boolean, default=False)  # Забрал ли награду

    # Связи
    user = relationship("User", back_populates="achievements")
    achievement = relationship("Achievement", back_populates="user_achievements")

    # Индексы
    __table_args__ = (
        UniqueConstraint('user_id', 'achievement_id', name='unique_user_achievement'),
        Index('idx_user_achievement', 'user_id', 'achievement_id'),
    )


class ShopItem(Base):
    """Товары в магазине с расширенным функционалом"""
    __tablename__ = "shop_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)

    # Цены
    price_coins = Column(Integer, nullable=False)
    price_gems = Column(Integer, default=0)
    discount_percentage = Column(Integer, default=0)  # Скидка в %

    # Категоризация
    item_type = Column(String(50), index=True)
    category = Column(String(50))
    tags = Column(JSON)

    # Данные товара
    item_data = Column(JSON)
    image_url = Column(String(500))
    preview_url = Column(String(500))

    # Доступность
    is_available = Column(Boolean, default=True, index=True)
    is_featured = Column(Boolean, default=False)
    is_limited = Column(Boolean, default=False)  # Ограниченное предложение
    stock = Column(Integer)  # None = бесконечно
    max_per_user = Column(Integer)  # Максимум на пользователя

    # Требования
    min_level = Column(Integer, default=1)
    required_achievements = Column(JSON)  # Необходимые достижения

    # Временные ограничения
    available_from = Column(DateTime)
    available_until = Column(DateTime)

    # Статистика
    purchases_count = Column(Integer, default=0)
    rating = Column(Float)

    # Метаданные
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Связи
    purchases = relationship("Purchase", back_populates="item", lazy="dynamic")

    # Индексы
    __table_args__ = (
        Index('idx_shop_item_type_available', 'item_type', 'is_available'),
        Index('idx_shop_item_featured', 'is_featured', 'is_available'),
    )


class Purchase(Base):
    """Покупки пользователей с расширенной информацией"""
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    item_id = Column(Integer, ForeignKey("shop_items.id"), nullable=False)

    # Цена на момент покупки
    price_coins = Column(Integer, nullable=False)
    price_gems = Column(Integer, default=0)
    discount_applied = Column(Integer, default=0)

    # Статус
    status = Column(String(20), default="completed")  # completed, refunded, pending

    # Метаданные
    purchased_at = Column(DateTime, default=func.now(), index=True)
    refunded_at = Column(DateTime)

    # Связи
    user = relationship("User", back_populates="purchases")
    item = relationship("ShopItem", back_populates="purchases")

    # Индексы
    __table_args__ = (
        Index('idx_purchase_user_item', 'user_id', 'item_id'),
        Index('idx_purchase_status', 'status', 'purchased_at'),
    )


class Transaction(Base):
    """История транзакций с детализацией"""
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # Суммы
    coins_amount = Column(Integer, default=0)
    gems_amount = Column(Integer, default=0)
    exp_amount = Column(Integer, default=0)

    # Тип и описание
    transaction_type = Column(String(50), nullable=False, index=True)
    category = Column(String(50))  # reward, purchase, bonus, penalty
    description = Column(String(255))

    # Баланс после транзакции
    coins_balance = Column(Integer)
    gems_balance = Column(Integer)

    # Связанные объекты
    related_submission_id = Column(Integer, ForeignKey("submissions.id"))
    related_purchase_id = Column(Integer, ForeignKey("purchases.id"))
    related_task_id = Column(Integer, ForeignKey("tasks.id"))

    # Метаданные
    created_at = Column(DateTime, default=func.now(), index=True)
    extra_data = Column(JSON)  # Дополнительная информация

    # Связи
    user = relationship("User", back_populates="transactions")

    # Индексы
    __table_args__ = (
        Index('idx_transaction_user_type', 'user_id', 'transaction_type'),
        Index('idx_transaction_created_at', 'created_at'),
    )


class Notification(Base):
    """Модель уведомлений"""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    type = Column(String(50))  # info, success, warning, error
    category = Column(String(50))  # task, achievement, shop, system

    # Статус
    is_read = Column(Boolean, default=False, index=True)
    is_deleted = Column(Boolean, default=False)

    # Действие
    action_url = Column(String(500))
    action_data = Column(JSON)

    # Временные метки
    created_at = Column(DateTime, default=func.now())
    read_at = Column(DateTime)
    expires_at = Column(DateTime)

    # Индексы
    __table_args__ = (
        Index('idx_notification_user_read', 'user_id', 'is_read'),
        Index('idx_notification_created_at', 'created_at'),
    )