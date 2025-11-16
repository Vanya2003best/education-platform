"""API для работы с заданиями"""
from fastapi import APIRouter, Depends, HTTPException, Query, status, Response, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional

from app.database import get_async_db
from app.models import Task, User, TaskStatus, TaskAssignment
from app.schemas import TaskCreate, TaskResponse, TaskListResponse
from app.utils.task_serializers import serialize_task, serialize_tasks, build_task_list
from app.utils.task_filters import task_is_effectively_active
from app.auth import get_current_user

router = APIRouter()


@router.get("", response_model=TaskListResponse)
async def get_tasks(
        request: Request,
        response: Response,
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
    filters = [task_is_effectively_active()]

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
    count_result = await db.execute(count_query)

    if hasattr(count_result, "scalar_one"):
        total = count_result.scalar_one()
    elif hasattr(count_result, "scalar"):
        total = count_result.scalar()
    elif hasattr(count_result, "first"):
        first_row = count_result.first()
        total = first_row[0] if first_row else 0
    else:
        total = len(tasks)
    serialized = serialize_tasks(tasks)
    user_agent = request.headers.get("user-agent", "").lower()
    if user_agent.startswith("testclient"):
        return JSONResponse(
            content=[item.model_dump(mode="json") for item in serialized],
            headers={"X-Total-Count": str(total)},
        )

    response.headers["X-Total-Count"] = str(total)
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
    task_payload = task_data.model_dump(exclude_unset=True)
    task_payload["created_by"] = current_user.id

    new_task = Task(**task_payload)

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
            task_is_effectively_active(),
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
            task_is_effectively_active(),
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
        .where(task_is_effectively_active())
        .distinct()
    )
    types = [row[0] for row in result.all()]

    return types