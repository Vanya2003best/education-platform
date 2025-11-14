"""
API для административных функций
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete, update, and_, or_
from typing import List, Optional
from datetime import datetime, timedelta

from app.database import get_async_db
from app.models import (
    User, Task, Submission, ShopItem, Achievement,
    Transaction, Notification, UserRole, SubmissionStatus,
    TaskAssignment, TaskStatus
)
from app.schemas import (
    AdminDashboard, BroadcastMessage, AdminTaskCreate,
    TaskResponse, TaskAssignmentRequest, AdminUserSummary, TaskListResponse
)
from app.auth import require_admin
from app.utils.cache import cache_manager
from app.utils.task_serializers import serialize_task, serialize_tasks
router = APIRouter()


@router.get("/dashboard", response_model=AdminDashboard)
async def get_admin_dashboard(
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Административная панель"""

    # Статистика пользователей
    total_users = await db.scalar(select(func.count(User.id)))
    active_users = await db.scalar(
        select(func.count(User.id)).where(User.is_active == True)
    )

    # Статистика за последние 24 часа
    day_ago = datetime.utcnow() - timedelta(days=1)

    new_users_24h = await db.scalar(
        select(func.count(User.id)).where(User.created_at >= day_ago)
    )

    active_users_24h = await db.scalar(
        select(func.count(User.id)).where(User.last_activity >= day_ago)
    )

    new_submissions_24h = await db.scalar(
        select(func.count(Submission.id)).where(
            Submission.submitted_at >= day_ago
        )
    )

    # Статистика контента
    total_tasks = await db.scalar(select(func.count(Task.id)))
    active_tasks = await db.scalar(
        select(func.count(Task.id)).where(Task.is_active == True)
    )

    total_submissions = await db.scalar(select(func.count(Submission.id)))

    # Экономика
    total_coins = await db.scalar(select(func.sum(User.coins))) or 0

    coins_earned_24h = await db.scalar(
        select(func.sum(Transaction.coins_amount)).where(
            and_(
                Transaction.created_at >= day_ago,
                Transaction.coins_amount > 0
            )
        )
    ) or 0

    coins_spent_24h = await db.scalar(
        select(func.sum(Transaction.coins_amount)).where(
            and_(
                Transaction.created_at >= day_ago,
                Transaction.coins_amount < 0
            )
        )
    ) or 0

    # Системная информация
    from app.utils.monitoring import get_system_metrics
    system_metrics = await get_system_metrics()

    return AdminDashboard(
        statistics={
            "users": {
                "total": total_users,
                "active": active_users,
                "new_24h": new_users_24h,
                "active_24h": active_users_24h
            },
            "content": {
                "total_tasks": total_tasks,
                "active_tasks": active_tasks,
                "total_submissions": total_submissions,
                "new_submissions_24h": new_submissions_24h
            }
        },
        economy={
            "total_coins": int(total_coins),
            "coins_earned_24h": int(coins_earned_24h),
            "coins_spent_24h": abs(int(coins_spent_24h))
        },
        system=system_metrics
    )


@router.post("/broadcast")
async def broadcast_message(
        message_data: BroadcastMessage,
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Отправить сообщение всем пользователям"""

    # Определяем целевую аудиторию
    query = select(User.id).where(User.is_active == True)

    if message_data.target == "students":
        query = query.where(User.role == UserRole.STUDENT)
    elif message_data.target == "teachers":
        query = query.where(User.role == UserRole.TEACHER)

    result = await db.execute(query)
    user_ids = [row[0] for row in result.all()]

    # Создаем уведомления
    notifications = [
        Notification(
            user_id=user_id,
            title=message_data.title,
            message=message_data.message,
            type="info",
            category="system"
        )
        for user_id in user_ids
    ]

    db.add_all(notifications)
    await db.commit()

    return {
        "message": "Сообщение отправлено",
        "recipients": len(user_ids)
    }

@router.get("/users/search", response_model=List[AdminUserSummary])
async def search_users(
        q: str = Query(..., min_length=1, max_length=100, description="Строка поиска"),
        limit: int = Query(15, ge=1, le=50),
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Поиск пользователей для назначения заданий"""

    search_value = q.strip()
    if not search_value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Строка поиска пуста")

    pattern = f"%{search_value}%"

    result = await db.execute(
        select(User)
        .where(
            or_(
                User.username.ilike(pattern),
                User.email.ilike(pattern),
                User.full_name.ilike(pattern)
            )
        )
        .order_by(User.username.asc())
        .limit(limit)
    )

    return result.scalars().all()


@router.post("/coins/grant")
async def grant_coins(
        user_id: int,
        amount: int,
        reason: str,
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Начислить монеты пользователю"""

    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден"
        )

    # Начисляем монеты
    user.coins += amount

    # Создаем транзакцию
    transaction = Transaction(
        user_id=user_id,
        coins_amount=amount,
        transaction_type="admin_grant",
        category="bonus",
        description=f"Начислено администратором: {reason}",
        coins_balance=user.coins
    )
    db.add(transaction)

    await db.commit()

    return {
        "message": f"Начислено {amount} монет",
        "new_balance": user.coins
    }
@router.get("/tasks", response_model=TaskListResponse)
async def get_admin_tasks(
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db),
        include_inactive: bool = Query(False, description="Возвращать ли неактивные задания"),
        subject: Optional[str] = Query(None, max_length=50),
        difficulty: Optional[int] = Query(None, ge=1, le=5),
        task_type: Optional[str] = Query(None, max_length=50),
        search: Optional[str] = Query(None, max_length=200),
        skip: int = Query(0, ge=0),
        limit: int = Query(50, ge=1, le=200)
):
    """Получить список заданий для административной панели"""

    filters = []

    if not include_inactive:
        filters.append(Task.status == TaskStatus.ACTIVE)

    if subject:
        filters.append(Task.subject == subject)

    if difficulty is not None:
        filters.append(Task.difficulty == difficulty)

    if task_type:
        filters.append(Task.task_type == task_type)

        query = select(Task)
        count_query = select(func.count(Task.id))

        if filters:
            query = query.where(*filters)
            count_query = count_query.where(*filters)

    if search:
        pattern = f"%{search.strip()}%"
        search_condition = or_(
            Task.title.ilike(pattern),
            Task.description.ilike(pattern),
            Task.subject.ilike(pattern)
        )
        query = query.where(search_condition)
        count_query = count_query.where(search_condition)

    result = await db.execute(
        query.order_by(Task.created_at.desc()).offset(skip).limit(limit)
    )
    tasks = result.scalars().all()
    total = await db.scalar(count_query) or 0
    serialized = serialize_tasks(tasks)
    return TaskListResponse(items=serialized, total=total)


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
        task_data: AdminTaskCreate,
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Создать новое задание и при необходимости назначить пользователям"""

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
    await db.flush()

    if task_data.assigned_user_ids:
        # Получаем список существующих пользователей
        result = await db.execute(
            select(User.id).where(User.id.in_(task_data.assigned_user_ids))
        )
        existing_user_ids = {row[0] for row in result.all()}
        missing_users = set(task_data.assigned_user_ids) - existing_user_ids

        if missing_users:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Пользователи не найдены: {sorted(missing_users)}"
            )

        existing_assignments = await db.execute(
            select(TaskAssignment.user_id).where(
                TaskAssignment.task_id == new_task.id,
                TaskAssignment.user_id.in_(existing_user_ids)
            )
        )
        already_assigned = {row[0] for row in existing_assignments.all()}
        new_assignments = [
            TaskAssignment(
                task_id=new_task.id,
                user_id=user_id,
                assigned_by=current_user.id
            )
            for user_id in existing_user_ids - already_assigned
        ]

        db.add_all(new_assignments)

    await db.commit()
    await db.refresh(new_task)

    await cache_manager.invalidate_pattern("tasks:*")

    return serialize_task(new_task)


@router.post("/tasks/{task_id}/assign")
async def assign_task(
        task_id: int,
        assignment: TaskAssignmentRequest,
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Назначить существующее задание выбранным пользователям"""

    result = await db.execute(select(Task).where(Task.id == task_id))
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Задание не найдено")

    result = await db.execute(
        select(User.id).where(User.id.in_(assignment.user_ids))
    )
    existing_user_ids = {row[0] for row in result.all()}
    missing_users = set(assignment.user_ids) - existing_user_ids

    if missing_users:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Пользователи не найдены: {sorted(missing_users)}"
        )

    existing_assignments = await db.execute(
        select(TaskAssignment.user_id).where(
            TaskAssignment.task_id == task_id,
            TaskAssignment.user_id.in_(existing_user_ids)
        )
    )
    already_assigned = {row[0] for row in existing_assignments.all()}

    new_assignments = [
        TaskAssignment(
            task_id=task_id,
            user_id=user_id,
            assigned_by=current_user.id
        )
        for user_id in existing_user_ids - already_assigned
    ]

    if new_assignments:
        db.add_all(new_assignments)

    await db.commit()

    await cache_manager.invalidate_pattern("tasks:*")

    return {
        "message": "Задание назначено",
        "task_id": task_id,
        "assigned_count": len(new_assignments)
    }

@router.post("/tasks/bulk-activate")
async def bulk_activate_tasks(
        task_ids: List[int],
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Массовая активация заданий"""

    await db.execute(
        update(Task)
        .where(Task.id.in_(task_ids))
        .values(is_active=True)
    )

    await db.commit()

    # Инвалидируем кэш
    await cache_manager.invalidate_pattern("tasks:*")

    return {
        "message": f"Активировано {len(task_ids)} заданий"
    }


@router.post("/tasks/bulk-deactivate")
async def bulk_deactivate_tasks(
        task_ids: List[int],
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Массовая деактивация заданий"""

    await db.execute(
        update(Task)
        .where(Task.id.in_(task_ids))
        .values(is_active=False)
    )

    await db.commit()

    await cache_manager.invalidate_pattern("tasks:*")

    return {
        "message": f"Деактивировано {len(task_ids)} заданий"
    }


@router.post("/submissions/{submission_id}/recheck")
async def recheck_submission(
        submission_id: int,
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Перепроверить сдачу"""

    result = await db.execute(
        select(Submission).where(Submission.id == submission_id)
    )
    submission = result.scalar_one_or_none()

    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сдача не найдена"
        )

    # Сбрасываем статус для повторной проверки
    submission.status = SubmissionStatus.PENDING
    submission.checked_at = None

    await db.commit()

    # Запускаем повторную проверку
    from app.services.ai_checker import ai_checker
    from app.routers.submissions import process_submission

    # TODO: Запустить фоновую задачу для перепроверки

    return {
        "message": "Сдача отправлена на повторную проверку",
        "submission_id": submission_id
    }


@router.post("/submissions/{submission_id}/manual-review")
async def set_manual_review(
        submission_id: int,
        score: Optional[float] = None,
        feedback: Optional[str] = None,
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Ручная оценка сдачи"""

    result = await db.execute(
        select(Submission).where(Submission.id == submission_id)
    )
    submission = result.scalar_one_or_none()

    if not submission:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Сдача не найдена"
        )

    # Обновляем оценку
    if score is not None:
        submission.manual_score = score
        submission.score = score  # Приоритет ручной оценке

    if feedback:
        submission.teacher_feedback = feedback

    submission.reviewed_by = current_user.id
    submission.reviewed_at = datetime.utcnow()
    submission.status = SubmissionStatus.CHECKED

    await db.commit()

    return {
        "message": "Ручная оценка проставлена",
        "score": score,
        "feedback": feedback
    }


@router.get("/logs/recent")
async def get_recent_logs(
        limit: int = 100,
        level: Optional[str] = None,
        current_user: User = Depends(require_admin)
):
    """Получить последние логи (требует настройки логирования)"""

    # TODO: Реализовать чтение логов из файла или БД

    return {
        "message": "Функция логирования в разработке",
        "logs": []
    }


@router.post("/cache/clear")
async def clear_cache(
        pattern: Optional[str] = None,
        current_user: User = Depends(require_admin)
):
    """Очистить кэш"""

    if pattern:
        count = await cache_manager.invalidate_pattern(pattern)
        return {
            "message": f"Удалено ключей: {count}",
            "pattern": pattern
        }
    else:
        # Очистить весь кэш (осторожно!)
        # await cache_manager.redis_client.flushdb()
        return {
            "message": "Используйте pattern для безопасной очистки"
        }


@router.get("/stats/database")
async def get_database_stats(
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Статистика базы данных"""

    from app.database import async_engine

    # Размеры таблиц
    tables_query = """
                   SELECT table_name, \
                          pg_total_relation_size(quote_ident(table_name)::regclass) as size
                   FROM information_schema.tables
                   WHERE table_schema = 'public'
                   ORDER BY size DESC \
                   """

    try:
        async with async_engine.connect() as conn:
            result = await conn.execute(tables_query)
            tables = [
                {"table": row[0], "size_bytes": row[1]}
                for row in result.all()
            ]
    except:
        tables = []

    return {
        "tables": tables,
        "connection_info": {
            "pool_size": async_engine.pool.size() if hasattr(async_engine, 'pool') else None
        }
    }


@router.post("/maintenance/optimize")
async def run_maintenance(
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Выполнить техническое обслуживание"""

    tasks = []

    # 1. Удалить старые уведомления (>30 дней)
    month_ago = datetime.utcnow() - timedelta(days=30)

    deleted_notifications = await db.execute(
        delete(Notification).where(
            and_(
                Notification.created_at < month_ago,
                Notification.is_read == True
            )
        )
    )

    tasks.append({
        "task": "delete_old_notifications",
        "deleted": deleted_notifications.rowcount
    })

    # 2. Обновить статистику заданий
    tasks_result = await db.execute(select(Task))
    for task in tasks_result.scalars().all():
        submissions = await db.scalar(
            select(func.count(Submission.id)).where(
                and_(
                    Submission.task_id == task.id,
                    Submission.status == SubmissionStatus.CHECKED
                )
            )
        )

        avg_score = await db.scalar(
            select(func.avg(Submission.score)).where(
                and_(
                    Submission.task_id == task.id,
                    Submission.status == SubmissionStatus.CHECKED
                )
            )
        )

        task.submissions_count = submissions or 0
        task.avg_score = round(avg_score, 1) if avg_score else 0

    tasks.append({
        "task": "update_task_statistics",
        "completed": True
    })

    await db.commit()

    # 3. Очистить старый кэш
    await cache_manager.invalidate_pattern("*:old:*")

    tasks.append({
        "task": "clear_old_cache",
        "completed": True
    })

    return {
        "message": "Техническое обслуживание завершено",
        "tasks": tasks
    }


@router.get("/health/detailed")
async def detailed_health_check(
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Детальная проверка здоровья системы"""

    checks = {}

    # Проверка БД
    try:
        await db.execute(select(1))
        checks["database"] = {"status": "healthy", "latency_ms": None}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)}

    # Проверка кэша
    if cache_manager.is_connected():
        try:
            start = datetime.utcnow()
            await cache_manager.set("health_check", "ok", ttl=10)
            latency = (datetime.utcnow() - start).total_seconds() * 1000
            checks["cache"] = {"status": "healthy", "latency_ms": round(latency, 2)}
        except Exception as e:
            checks["cache"] = {"status": "unhealthy", "error": str(e)}
    else:
        checks["cache"] = {"status": "not_configured"}

    # Проверка AI сервиса
    from app.config import settings
    checks["ai_service"] = {
        "status": "configured" if settings.OPENAI_API_KEY else "not_configured"
    }

    # Общий статус
    overall_status = "healthy"
    if any(check.get("status") == "unhealthy" for check in checks.values()):
        overall_status = "unhealthy"
    elif any(check.get("status") == "degraded" for check in checks.values()):
        overall_status = "degraded"

    return {
        "overall_status": overall_status,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat()
    }