"""
API для работы с заданиями
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.database import get_db
from app.models import Task, User
from app.schemas import TaskCreate, TaskResponse
from app.auth import get_current_user

router = APIRouter()


@router.get("/", response_model=List[TaskResponse])
async def get_tasks(
        skip: int = 0,
        limit: int = 20,
        subject: Optional[str] = None,
        difficulty: Optional[int] = Query(None, ge=1, le=5),
        task_type: Optional[str] = None,
        db: Session = Depends(get_db)
):
    """
    Получить список заданий с фильтрами
    """
    query = db.query(Task).filter(Task.is_active == True)

    # Фильтры
    if subject:
        query = query.filter(Task.subject == subject)

    if difficulty:
        query = query.filter(Task.difficulty == difficulty)

    if task_type:
        query = query.filter(Task.task_type == task_type)

    tasks = query.order_by(Task.created_at.desc()).offset(skip).limit(limit).all()

    return tasks


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: int, db: Session = Depends(get_db)):
    """
    Получить конкретное задание
    """
    task = db.query(Task).filter(Task.id == task_id).first()

    if not task:
        raise HTTPException(status_code=404, detail="Задание не найдено")

    return task


@router.post("/", response_model=TaskResponse)
async def create_task(
        task_data: TaskCreate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Создать новое задание (для учителей/администраторов)
    В продакшене добавить проверку роли
    """
    new_task = Task(
        title=task_data.title,
        description=task_data.description,
        task_type=task_data.task_type,
        subject=task_data.subject,
        difficulty=task_data.difficulty,
        reward_coins=task_data.reward_coins,
        reward_exp=task_data.reward_exp,
        checking_criteria=task_data.checking_criteria,
        example_solution=task_data.example_solution,
        created_by=current_user.id
    )

    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    return new_task


@router.get("/subjects/list")
async def get_subjects(db: Session = Depends(get_db)):
    """
    Получить список доступных предметов
    """
    subjects = db.query(Task.subject).filter(
        Task.subject.isnot(None),
        Task.is_active == True
    ).distinct().all()

    return [s[0] for s in subjects if s[0]]


@router.get("/types/list")
async def get_task_types(db: Session = Depends(get_db)):
    """
    Получить список типов заданий
    """
    types = db.query(Task.task_type).filter(
        Task.is_active == True
    ).distinct().all()

    return [t[0] for t in types]