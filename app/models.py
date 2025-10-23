"""
Модели базы данных
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()


class User(Base):
    """Модель пользователя (ученика)"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100))

    # Игровые показатели
    coins = Column(Integer, default=0)
    level = Column(Integer, default=1)
    experience = Column(Integer, default=0)

    # Статистика
    tasks_completed = Column(Integer, default=0)
    average_score = Column(Float, default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, default=datetime.utcnow)

    # Связи
    submissions = relationship("Submission", back_populates="user")
    purchases = relationship("Purchase", back_populates="user")


class Task(Base):
    """Модель задания"""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)

    # Тип задания
    task_type = Column(String(50), nullable=False)  # 'math', 'essay', 'code', 'physics', etc
    subject = Column(String(50))  # математика, физика, русский язык

    # Сложность и награды
    difficulty = Column(Integer, default=1)  # 1-5
    reward_coins = Column(Integer, default=10)
    reward_exp = Column(Integer, default=50)

    # Критерии проверки (JSON)
    checking_criteria = Column(Text)  # JSON с критериями для AI

    # Примеры правильного решения
    example_solution = Column(Text)

    # Метаданные
    created_by = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    # Связи
    submissions = relationship("Submission", back_populates="task")


class Submission(Base):
    """Модель сдачи работы (с фото)"""
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)

    # Загруженное фото работы
    photo_url = Column(String(500), nullable=False)
    photo_filename = Column(String(255))

    # Распознанный текст
    recognized_text = Column(Text)

    # Результаты проверки
    score = Column(Integer, default=0)  # 0-100
    status = Column(String(20), default="pending")  # pending, processing, checked, failed

    # AI feedback
    ai_feedback = Column(Text)
    detailed_analysis = Column(Text)  # JSON с детальным разбором

    # Награды
    coins_earned = Column(Integer, default=0)
    exp_earned = Column(Integer, default=0)

    # Время
    submitted_at = Column(DateTime, default=datetime.utcnow)
    checked_at = Column(DateTime)
    processing_time = Column(Float)  # секунды обработки

    # Связи
    user = relationship("User", back_populates="submissions")
    task = relationship("Task", back_populates="submissions")


class ShopItem(Base):
    """Товары в магазине"""
    __tablename__ = "shop_items"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    price = Column(Integer, nullable=False)

    # Тип товара
    item_type = Column(String(50))  # 'avatar', 'badge', 'theme', 'power_up', 'hint'

    # Данные товара (JSON)
    item_data = Column(Text)  # URL аватара, код темы и т.д.

    # Изображение
    image_url = Column(String(255))

    # Доступность
    available = Column(Boolean, default=True)
    stock = Column(Integer)  # None = бесконечно

    created_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    purchases = relationship("Purchase", back_populates="item")


class Purchase(Base):
    """Покупки пользователей"""
    __tablename__ = "purchases"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("shop_items.id"), nullable=False)

    price_paid = Column(Integer, nullable=False)
    purchased_at = Column(DateTime, default=datetime.utcnow)

    # Связи
    user = relationship("User", back_populates="purchases")
    item = relationship("ShopItem", back_populates="purchases")


class Transaction(Base):
    """История транзакций монет"""
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    amount = Column(Integer, nullable=False)  # + или -
    transaction_type = Column(String(50))  # 'task_reward', 'purchase', 'bonus', 'penalty'
    description = Column(String(255))

    # Связанные объекты
    related_submission_id = Column(Integer, ForeignKey("submissions.id"))
    related_purchase_id = Column(Integer, ForeignKey("purchases.id"))

    created_at = Column(DateTime, default=datetime.utcnow)