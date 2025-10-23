"""
Pydantic схемы для валидации данных API
"""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


# ===== USER SCHEMAS =====

class UserBase(BaseModel):
    username: str
    email: EmailStr


class UserCreate(UserBase):
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(UserBase):
    id: int
    full_name: Optional[str]
    coins: int
    level: int
    experience: int
    tasks_completed: int
    average_score: float
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


# ===== TASK SCHEMAS =====

class TaskBase(BaseModel):
    title: str
    description: str
    task_type: str
    subject: Optional[str] = None
    difficulty: int = Field(default=1, ge=1, le=5)


class TaskCreate(TaskBase):
    reward_coins: int = 10
    reward_exp: int = 50
    checking_criteria: Optional[str] = None
    example_solution: Optional[str] = None


class TaskResponse(TaskBase):
    id: int
    reward_coins: int
    reward_exp: int
    difficulty: int
    created_at: datetime
    is_active: bool

    class Config:
        from_attributes = True


# ===== SUBMISSION SCHEMAS =====

class SubmissionResponse(BaseModel):
    id: int
    status: str
    message: Optional[str] = None


class SubmissionDetail(BaseModel):
    id: int
    user_id: int
    task_id: int
    photo_url: str
    recognized_text: Optional[str]
    score: int
    status: str
    ai_feedback: Optional[str]
    coins_earned: int
    exp_earned: int
    submitted_at: datetime
    checked_at: Optional[datetime]
    processing_time: Optional[float]

    class Config:
        from_attributes = True


# ===== SHOP SCHEMAS =====

class ShopItemBase(BaseModel):
    name: str
    description: Optional[str]
    price: int
    item_type: str


class ShopItemCreate(ShopItemBase):
    item_data: Optional[str] = None
    image_url: Optional[str] = None
    stock: Optional[int] = None


class ShopItemResponse(ShopItemBase):
    id: int
    image_url: Optional[str]
    available: bool
    stock: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


class PurchaseCreate(BaseModel):
    item_id: int


class PurchaseResponse(BaseModel):
    id: int
    user_id: int
    item_id: int
    price_paid: int
    purchased_at: datetime

    class Config:
        from_attributes = True


# ===== STATISTICS SCHEMAS =====

class UserStats(BaseModel):
    total_submissions: int
    average_score: float
    total_coins_earned: int
    tasks_completed: int
    current_level: int
    experience: int
    next_level_exp: int


class LeaderboardEntry(BaseModel):
    rank: int
    username: str
    level: int
    experience: int
    average_score: float
    tasks_completed: int