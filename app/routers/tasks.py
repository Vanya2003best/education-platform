"""API для работы с заданиями"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional

from app.database import get_async_db
from app.models import Task, User, TaskStatus, TaskAssignment
from app.schemas import TaskCreate, TaskResponse, TaskListResponse
from app.utils.task_serializers import serialize_task, serialize_tasks, build_task_list
from app.auth import get_current_user

router = APIRouter()


@router.get("", response_model=TaskListResponse)
async def get_tasks(
        skip: int = 0,
        limit: int = 20,
        subject: Optional[str] = None,
        difficulty: Optional[int] = Query(None, ge=1, le=5),
        task_type: Optional[str] = None,
        db: AsyncSession = Depends(get_async_db)
):
    """
    Получить список заданий с фильтрами
    """
    filters = [Task.status == TaskStatus.ACTIVE]

    # Фильтры
    if subject:
        filters.append(Task.subject == subject)

    if difficulty:
        filters.append(Task.difficulty == difficulty)

    if task_type:
        filters.append(Task.task_type == task_type)
        base_query = select(Task).where(*filters)
        count_query = select(func.count(Task.id)).where(*filters)

    result = await db.execute(
        base_query.order_by(Task.created_at.desc()).offset(skip).limit(limit)
    )
    tasks = result.scalars().all()
    total = await db.scalar(count_query) or 0
    serialized = serialize_tasks(tasks)
    return TaskListResponse(items=serialized, total=total)


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
        task_data: TaskCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db)
):
    """
    Создать новое задание (для учителей/администраторов)
    """
    new_task = Task(
        title=task_data.title,
        description=task_data.description,
        content_html=task_data.content_html,
        task_type=task_data.task_type,
        subject=task_data.subject,
        topic=task_data.topic,
        tags=task_data.tags,
        difficulty=task_data.difficulty,
        min_level=task_data.min_level,
        time_limit=task_data.time_limit,
        max_attempts=task_data.max_attempts,
        reward_coins=task_data.reward_coins,
        reward_exp=task_data.reward_exp,
        reward_gems=task_data.reward_gems,
        checking_criteria=task_data.checking_criteria,
        example_solution=task_data.example_solution,
        hints=task_data.hints,
        resources=task_data.resources,
        image_url=task_data.image_url,
        video_url=task_data.video_url,
        created_by=current_user.id
    )

    db.add(new_task)
    await db.commit()
    await db.refresh(new_task)

    return serialize_task(new_task)

@router.get("/assigned", response_model=TaskListResponse)
async def get_assigned_tasks(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db)
):
    """Получить список заданий, назначенных текущему пользователю"""

    result = await db.execute(
        select(Task)
        .join(TaskAssignment, TaskAssignment.task_id == Task.id)
        .where(
            TaskAssignment.user_id == current_user.id,
            Task.status == TaskStatus.ACTIVE
        )
        .order_by(TaskAssignment.assigned_at.desc())
    )

    tasks = result.scalars().all()

    return build_task_list(tasks)


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
        task_id: int,
        db: AsyncSession = Depends(get_async_db)
):
    """
    Получить конкретное задание
    """
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Задание не найдено")

    return serialize_task(task)

@router.get("/subjects/list")
async def get_subjects(db: AsyncSession = Depends(get_async_db)):
    """
    Получить список доступных предметов
    """
    result = await db.execute(
        select(Task.subject)
        .where(
            Task.subject.isnot(None),
            Task.status == TaskStatus.ACTIVE
        )
        .distinct()
    )
    subjects = [row[0] for row in result.all() if row[0]]

    return subjects


@router.get("/types/list")
async def get_task_types(db: AsyncSession = Depends(get_async_db)):
    """
    Получить список типов заданий
    """
    result = await db.execute(
        select(Task.task_type)
        .where(Task.status == TaskStatus.ACTIVE)
        .distinct()
    )
    types = [row[0] for row in result.all()]

    return types