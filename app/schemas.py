"""
Pydantic схемы для валидации данных API
"""
from pydantic import BaseModel, EmailStr, Field, ConfigDict, ValidationInfo, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ===== ENUMS =====

class UserRoleEnum(str, Enum):
    STUDENT = "student"
    TEACHER = "teacher"
    ADMIN = "admin"
    PARENT = "parent"


class TaskTypeEnum(str, Enum):
    MATH = "math"
    ESSAY = "essay"
    PHYSICS = "physics"
    CHEMISTRY = "chemistry"
    BIOLOGY = "biology"
    HISTORY = "history"
    GEOGRAPHY = "geography"
    LITERATURE = "literature"
    CODE = "code"
    ART = "art"


class SubmissionStatusEnum(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    CHECKED = "checked"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


# ===== USER SCHEMAS =====

class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: Optional[str] = Field(None, max_length=100)


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=100)

    @field_validator('password')
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not any(c.isupper() for c in v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Password must contain at least one digit')
        return v


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    bio: Optional[str] = None
    grade: Optional[int] = Field(None, ge=1, le=12)
    school: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None
    timezone: Optional[str] = None
    language: Optional[str] = None
    email_notifications: Optional[bool] = None
    push_notifications: Optional[bool] = None
    theme: Optional[str] = None


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)  # ВАЖНО

    id: int
    username: str
    email: str
    full_name: str | None = None
    role: str | None = None
    coins: int
    level: int
    experience: int
    is_active: bool = True
    is_verified: bool = False
    last_login: datetime | None = None
    last_activity: datetime | None = None


class UserStats(BaseModel):
    user_id: int
    total_submissions: int
    successful_submissions: int
    success_rate: float
    week_submissions: int
    total_coins_earned: int
    achievements_unlocked: int
    current_streak: int
    best_score: float
    total_time_spent: int
    rank_position: int

class UserLogin(BaseModel):
    username: str
    password: str


class PasswordChange(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=8)

    @field_validator('new_password')
    def passwords_different(cls, v: str, info: ValidationInfo) -> str:
        old_password = info.data.get('old_password') if info.data else None
        if old_password and v == old_password:
            raise ValueError('New password must be different from old password')
        return v


class Token(BaseModel):
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"


class TokenData(BaseModel):
    user_id: Optional[int] = None
    role: Optional[str] = None


# ===== TASK SCHEMAS =====

class TaskBase(BaseModel):
    title: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=10)
    task_type: str = Field(..., min_length=1, max_length=50)
    subject: Optional[str] = Field(None, max_length=50)
    difficulty: int = Field(1, ge=1, le=5)
    content_html: Optional[str] = None

    @field_validator("task_type", mode="before")
    def normalize_task_type(cls, value: Any) -> str:
        """Normalize task_type values from a variety of legacy sources."""
        if value is None:
            return "general"

        if isinstance(value, TaskTypeEnum):
            return value.value

        if isinstance(value, str):
            normalized = value.strip()
            return normalized or "general"

        try:
            normalized = str(value).strip()
        except Exception as exc:  # pragma: no cover - extremely defensive
            raise ValueError("Invalid task_type value") from exc

        return normalized or "general"

class TaskCreate(TaskBase):
    topic: Optional[str] = None
    tags: Optional[List[str]] = None
    min_level: int = Field(1, ge=1)
    time_limit: Optional[int] = Field(None, ge=1)
    max_attempts: int = Field(3, ge=1)
    reward_coins: int = Field(10, ge=0)
    reward_exp: int = Field(50, ge=0)
    reward_gems: int = Field(0, ge=0)
    checking_criteria: Optional[Dict[str, Any]] = None
    example_solution: Optional[str] = None
    hints: Optional[List[str]] = None
    resources: Optional[List[str]] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None

class AdminTaskCreate(TaskCreate):
    assigned_user_ids: Optional[List[int]] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    difficulty: Optional[int] = Field(None, ge=1, le=5)
    reward_coins: Optional[int] = Field(None, ge=0)
    reward_exp: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None
    content_html: Optional[str] = None

class TaskResponse(TaskBase):
    id: int
    status: str = Field(default="active")
    is_admin_task: bool = False
    topic: Optional[str]
    tags: Optional[List[str]]
    min_level: int
    time_limit: Optional[int]
    max_attempts: int
    reward_coins: int
    reward_exp: int
    reward_gems: int
    bonus_coins: int
    image_url: Optional[str]
    video_url: Optional[str]
    is_premium: bool
    is_featured: bool
    submissions_count: int
    success_rate: float
    avg_score: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
class TaskListResponse(BaseModel):
    """Унифицированный список заданий с общей статистикой."""

    items: List[TaskResponse]
    total: int
class TaskAssignmentRequest(BaseModel):
    user_ids: List[int] = Field(..., min_length=1)
# ===== SUBMISSION SCHEMAS =====

class SubmissionCreate(BaseModel):
    task_id: int
    user_answer: Optional[str] = None
    device_info: Optional[Dict[str, Any]] = None


class SubmissionResponse(BaseModel):
    id: int
    user_id: int
    task_id: int
    photo_urls: Optional[List[str]]
    recognized_text: Optional[str]
    score: float
    status: SubmissionStatusEnum
    ai_feedback: Optional[str]
    confidence_score: Optional[float]
    plagiarism_score: Optional[float]
    coins_earned: int
    exp_earned: int
    gems_earned: int
    submitted_at: datetime
    checked_at: Optional[datetime]
    processing_time: Optional[float]
    attempt_number: int

    model_config = ConfigDict(from_attributes=True)


class SubmissionDetail(SubmissionResponse):
    task: Optional[TaskResponse]
    detailed_analysis: Optional[Dict[str, Any]]
    achievements_unlocked: Optional[List[str]]
    teacher_feedback: Optional[str]
    reviewed_at: Optional[datetime]

class HtmlSubmissionRequest(BaseModel):
    """Результат выполнения задания в HTML-формате."""

    task_id: int
    score: float = Field(..., ge=0)
    max_score: Optional[float] = Field(None, gt=0)
    time_spent: Optional[int] = Field(None, ge=0)
    result_text: Optional[str] = Field(None, max_length=2000)
    details: Optional[Dict[str, Any]] = None


class HtmlSubmissionResponse(BaseModel):
    """Ответ после фиксации результата HTML-задания."""

    submission_id: int
    coins_earned: int
    exp_earned: int
    new_level: int
    total_coins: int
    message: str


# ===== SHOP SCHEMAS =====

class ShopItemBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    price_coins: int = Field(..., ge=0)
    price_gems: int = Field(0, ge=0)
    item_type: str
    category: Optional[str] = None


class ShopItemCreate(ShopItemBase):
    tags: Optional[List[str]] = None
    item_data: Optional[Dict[str, Any]] = None
    image_url: Optional[str] = None
    preview_url: Optional[str] = None
    stock: Optional[int] = None
    max_per_user: Optional[int] = None
    min_level: int = Field(1, ge=1)
    required_achievements: Optional[List[int]] = None
    available_from: Optional[datetime] = None
    available_until: Optional[datetime] = None


class ShopItemResponse(ShopItemBase):
    id: int
    discount_percentage: int
    tags: Optional[List[str]]
    image_url: Optional[str]
    is_available: bool
    is_featured: bool
    is_limited: bool
    stock: Optional[int]
    purchases_count: int
    rating: Optional[float]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PurchaseCreate(BaseModel):
    item_id: int


class PurchaseResponse(BaseModel):
    id: int
    user_id: int
    item_id: int
    price_coins: int
    price_gems: int
    discount_applied: int
    status: str
    purchased_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ===== ACHIEVEMENT SCHEMAS =====

class AchievementBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    icon_url: Optional[str] = None
    category: str = Field("special")
    rarity: str = Field("common")


class AchievementCreate(AchievementBase):
    criteria: Optional[Dict[str, Any]] = None
    points: int = Field(10, ge=0)
    reward_coins: int = Field(0, ge=0)
    reward_gems: int = Field(0, ge=0)
    reward_exp: int = Field(0, ge=0)
    is_hidden: bool = Field(False)


class AchievementResponse(AchievementBase):
    id: int
    points: int
    reward_coins: int
    reward_gems: int
    reward_exp: int
    is_hidden: bool
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserAchievementResponse(BaseModel):
    achievement: AchievementResponse
    unlocked_at: datetime
    progress: int
    is_claimed: bool

    model_config = ConfigDict(from_attributes=True)


# ===== ANALYTICS SCHEMAS =====

class PlatformOverview(BaseModel):
    total_users: int
    total_tasks: int
    total_submissions: int
    active_users_24h: int
    average_score: float
    top_subjects: List[Dict[str, Any]]
    platform_health: str


class UserProgress(BaseModel):
    period: str
    daily_stats: List[Dict[str, Any]]
    total_submissions: int
    average_score: float
    coins_earned: int
    coins_spent: int
    net_coins: int


class SubjectPerformance(BaseModel):
    subjects: List[Dict[str, Any]]
    best_subject: Optional[str]
    needs_improvement: List[str]


class LearningCurve(BaseModel):
    data_points: List[Dict[str, Any]]
    total_submissions: int
    current_average: float
    improvement: float
    trend: str


# ===== NOTIFICATION SCHEMAS =====

class NotificationCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    message: str
    type: str = Field("info")
    category: str = Field("system")
    action_url: Optional[str] = None
    action_data: Optional[Dict[str, Any]] = None
    expires_at: Optional[datetime] = None


class NotificationResponse(NotificationCreate):
    id: int
    user_id: int
    is_read: bool
    created_at: datetime
    read_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


# ===== LEADERBOARD SCHEMAS =====

class LeaderboardEntry(BaseModel):
    rank: int
    user_id: int
    username: str
    avatar_url: Optional[str]
    level: int
    experience: int
    tasks_completed: int
    average_score: float
    total_points: Optional[int] = None
    achievements_count: Optional[int] = None


# ===== TRANSACTION SCHEMAS =====

class TransactionResponse(BaseModel):
    id: int
    user_id: int
    coins_amount: int
    gems_amount: int
    exp_amount: int
    transaction_type: str
    category: str
    description: str
    coins_balance: Optional[int]
    gems_balance: Optional[int]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ===== ADMIN SCHEMAS =====

class AdminDashboard(BaseModel):
    statistics: Dict[str, Any]
    economy: Dict[str, Any]
    system: Dict[str, Any]


class BroadcastMessage(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    message: str
    target: str = Field("all", pattern="^(all|students|teachers)$")


class AdminUserSummary(BaseModel):
    id: int
    username: str
    email: str
    role: str

    model_config = ConfigDict(from_attributes=True)