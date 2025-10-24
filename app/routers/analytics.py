"""
API для аналитики и статистики
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc
from typing import List, Optional
from datetime import datetime, timedelta

from app.database import get_async_db
from app.models import (
    User, Task, Submission, Transaction,
    UserRole, SubmissionStatus
)
from app.schemas import (
    PlatformOverview, UserProgress, SubjectPerformance,
    LearningCurve
)
from app.auth import get_current_user, require_admin
from app.utils.cache import cache_result

router = APIRouter()


@router.get("/overview", response_model=PlatformOverview)
@cache_result("platform_overview", ttl=300)
async def get_platform_overview(
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Общая статистика платформы (только для админов)"""

    # Общее количество пользователей
    total_users = await db.scalar(
        select(func.count(User.id))
    )

    # Активные за последние 24 часа
    day_ago = datetime.utcnow() - timedelta(days=1)
    active_users = await db.scalar(
        select(func.count(User.id)).where(
            User.last_activity >= day_ago
        )
    )

    # Общее количество заданий
    total_tasks = await db.scalar(
        select(func.count(Task.id))
    )

    # Общее количество сдач
    total_submissions = await db.scalar(
        select(func.count(Submission.id))
    )

    # Средний балл
    avg_score = await db.scalar(
        select(func.avg(Submission.score)).where(
            Submission.status == SubmissionStatus.CHECKED
        )
    )

    # Топ предметов по количеству заданий
    subjects_result = await db.execute(
        select(
            Task.subject,
            func.count(Task.id).label('count')
        )
        .where(Task.subject.isnot(None))
        .group_by(Task.subject)
        .order_by(desc('count'))
        .limit(5)
    )

    top_subjects = [
        {"subject": row[0], "count": row[1]}
        for row in subjects_result.all()
    ]

    # Определяем здоровье платформы
    health = "healthy"
    if active_users / total_users < 0.1 if total_users > 0 else True:
        health = "needs_attention"
    elif avg_score and avg_score < 50:
        health = "degraded"

    return PlatformOverview(
        total_users=total_users or 0,
        total_tasks=total_tasks or 0,
        total_submissions=total_submissions or 0,
        active_users_24h=active_users or 0,
        average_score=round(avg_score, 1) if avg_score else 0,
        top_subjects=top_subjects,
        platform_health=health
    )


@router.get("/my/progress", response_model=UserProgress)
async def get_user_progress(
        period: str = Query("week", regex="^(week|month|year)$"),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db)
):
    """Прогресс пользователя за период"""

    # Определяем временной диапазон
    if period == "week":
        days = 7
    elif period == "month":
        days = 30
    else:  # year
        days = 365

    start_date = datetime.utcnow() - timedelta(days=days)

    # Получаем сдачи за период
    submissions_result = await db.execute(
        select(Submission).where(
            and_(
                Submission.user_id == current_user.id,
                Submission.submitted_at >= start_date
            )
        ).order_by(Submission.submitted_at)
    )
    submissions = submissions_result.scalars().all()

    # Группируем по дням
    daily_stats = {}
    for sub in submissions:
        day = sub.submitted_at.date().isoformat()

        if day not in daily_stats:
            daily_stats[day] = {
                "date": day,
                "submissions": 0,
                "total_score": 0,
                "coins_earned": 0
            }

        daily_stats[day]["submissions"] += 1
        daily_stats[day]["total_score"] += sub.score or 0
        daily_stats[day]["coins_earned"] += sub.coins_earned or 0

    # Вычисляем средние баллы
    for day in daily_stats:
        count = daily_stats[day]["submissions"]
        if count > 0:
            daily_stats[day]["average_score"] = round(
                daily_stats[day]["total_score"] / count, 1
            )

    # Транзакции за период
    transactions_result = await db.execute(
        select(Transaction).where(
            and_(
                Transaction.user_id == current_user.id,
                Transaction.created_at >= start_date
            )
        )
    )
    transactions = transactions_result.scalars().all()

    coins_earned = sum(t.coins_amount for t in transactions if t.coins_amount > 0)
    coins_spent = abs(sum(t.coins_amount for t in transactions if t.coins_amount < 0))

    return UserProgress(
        period=period,
        daily_stats=list(daily_stats.values()),
        total_submissions=len(submissions),
        average_score=round(sum(s.score for s in submissions) / len(submissions), 1) if submissions else 0,
        coins_earned=coins_earned,
        coins_spent=coins_spent,
        net_coins=coins_earned - coins_spent
    )


@router.get("/my/subjects", response_model=SubjectPerformance)
async def get_subject_performance(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db)
):
    """Анализ по предметам"""

    # Получаем статистику по каждому предмету
    subjects_result = await db.execute(
        select(
            Task.subject,
            func.count(Submission.id).label('submissions'),
            func.avg(Submission.score).label('avg_score'),
            func.max(Submission.score).label('max_score')
        )
        .join(Task, Submission.task_id == Task.id)
        .where(
            and_(
                Submission.user_id == current_user.id,
                Submission.status == SubmissionStatus.CHECKED,
                Task.subject.isnot(None)
            )
        )
        .group_by(Task.subject)
    )

    subjects_data = []
    best_subject = None
    best_score = 0
    needs_improvement = []

    for row in subjects_result.all():
        subject_name = row[0]
        submissions_count = row[1]
        avg_score = round(row[2], 1) if row[2] else 0
        max_score = row[3] or 0

        subjects_data.append({
            "subject": subject_name,
            "submissions": submissions_count,
            "average_score": avg_score,
            "max_score": max_score
        })

        # Определяем лучший предмет
        if avg_score > best_score:
            best_score = avg_score
            best_subject = subject_name

        # Предметы, требующие внимания
        if avg_score < 60:
            needs_improvement.append(subject_name)

    return SubjectPerformance(
        subjects=subjects_data,
        best_subject=best_subject,
        needs_improvement=needs_improvement
    )


@router.get("/my/learning-curve", response_model=LearningCurve)
async def get_learning_curve(
        limit: int = Query(50, ge=10, le=200),
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db)
):
    """Кривая обучения - динамика оценок"""

    # Получаем последние сдачи
    submissions_result = await db.execute(
        select(Submission)
        .where(
            and_(
                Submission.user_id == current_user.id,
                Submission.status == SubmissionStatus.CHECKED
            )
        )
        .order_by(Submission.submitted_at.desc())
        .limit(limit)
    )
    submissions = list(reversed(submissions_result.scalars().all()))

    if not submissions:
        return LearningCurve(
            data_points=[],
            total_submissions=0,
            current_average=0,
            improvement=0,
            trend="stable"
        )

    # Формируем точки данных
    data_points = []
    running_avg = []

    for i, sub in enumerate(submissions, 1):
        running_avg.append(sub.score)

        data_points.append({
            "submission_number": i,
            "score": sub.score,
            "moving_average": round(sum(running_avg[-10:]) / len(running_avg[-10:]), 1),
            "date": sub.submitted_at.isoformat()
        })

    # Анализ тренда
    current_avg = sum(s.score for s in submissions[-10:]) / min(10, len(submissions))

    if len(submissions) > 10:
        old_avg = sum(s.score for s in submissions[:10]) / 10
        improvement = current_avg - old_avg
    else:
        improvement = 0

    # Определяем тренд
    if improvement > 5:
        trend = "improving"
    elif improvement < -5:
        trend = "declining"
    else:
        trend = "stable"

    return LearningCurve(
        data_points=data_points,
        total_submissions=len(submissions),
        current_average=round(current_avg, 1),
        improvement=round(improvement, 1),
        trend=trend
    )


@router.get("/tasks/{task_id}/stats")
async def get_task_statistics(
        task_id: int,
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Статистика по конкретному заданию"""

    # Проверяем существование задания
    task_result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = task_result.scalar_one_or_none()

    if not task:
        from fastapi import HTTPException, status
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Задание не найдено"
        )

    # Общая статистика
    submissions_result = await db.execute(
        select(Submission).where(
            and_(
                Submission.task_id == task_id,
                Submission.status == SubmissionStatus.CHECKED
            )
        )
    )
    submissions = submissions_result.scalars().all()

    if not submissions:
        return {
            "task_id": task_id,
            "title": task.title,
            "total_submissions": 0,
            "average_score": 0,
            "success_rate": 0,
            "score_distribution": {}
        }

    # Вычисляем метрики
    scores = [s.score for s in submissions]
    avg_score = sum(scores) / len(scores)
    success_count = sum(1 for s in scores if s >= 50)
    success_rate = success_count / len(scores) * 100

    # Распределение оценок
    score_distribution = {
        "0-20": 0,
        "21-40": 0,
        "41-60": 0,
        "61-80": 0,
        "81-100": 0
    }

    for score in scores:
        if score <= 20:
            score_distribution["0-20"] += 1
        elif score <= 40:
            score_distribution["21-40"] += 1
        elif score <= 60:
            score_distribution["41-60"] += 1
        elif score <= 80:
            score_distribution["61-80"] += 1
        else:
            score_distribution["81-100"] += 1

    # Топ пользователей
    top_users_result = await db.execute(
        select(
            User.username,
            Submission.score
        )
        .join(Submission, User.id == Submission.user_id)
        .where(
            and_(
                Submission.task_id == task_id,
                Submission.status == SubmissionStatus.CHECKED
            )
        )
        .order_by(desc(Submission.score))
        .limit(10)
    )

    top_users = [
        {"username": row[0], "score": row[1]}
        for row in top_users_result.all()
    ]

    return {
        "task_id": task_id,
        "title": task.title,
        "subject": task.subject,
        "difficulty": task.difficulty,
        "total_submissions": len(submissions),
        "average_score": round(avg_score, 1),
        "success_rate": round(success_rate, 1),
        "score_distribution": score_distribution,
        "top_performers": top_users,
        "median_score": sorted(scores)[len(scores) // 2],
        "min_score": min(scores),
        "max_score": max(scores)
    }


@router.get("/users/activity")
async def get_users_activity(
        days: int = Query(7, ge=1, le=90),
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Активность пользователей за период"""

    start_date = datetime.utcnow() - timedelta(days=days)

    # Активность по дням
    daily_activity_result = await db.execute(
        select(
            func.date(Submission.submitted_at).label('date'),
            func.count(func.distinct(Submission.user_id)).label('active_users'),
            func.count(Submission.id).label('submissions')
        )
        .where(Submission.submitted_at >= start_date)
        .group_by(func.date(Submission.submitted_at))
        .order_by('date')
    )

    daily_activity = [
        {
            "date": row[0].isoformat(),
            "active_users": row[1],
            "submissions": row[2]
        }
        for row in daily_activity_result.all()
    ]

    # Самые активные пользователи
    top_active_result = await db.execute(
        select(
            User.username,
            func.count(Submission.id).label('submissions')
        )
        .join(Submission, User.id == Submission.user_id)
        .where(Submission.submitted_at >= start_date)
        .group_by(User.id, User.username)
        .order_by(desc('submissions'))
        .limit(10)
    )

    top_active = [
        {"username": row[0], "submissions": row[1]}
        for row in top_active_result.all()
    ]

    return {
        "period_days": days,
        "daily_activity": daily_activity,
        "top_active_users": top_active
    }


@router.get("/economy")
async def get_economy_stats(
        current_user: User = Depends(require_admin),
        db: AsyncSession = Depends(get_async_db)
):
    """Статистика внутренней экономики"""

    # Общее количество монет в системе
    total_coins_result = await db.scalar(
        select(func.sum(User.coins))
    )
    total_coins = total_coins_result or 0

    # Всего заработано
    earned_result = await db.scalar(
        select(func.sum(Transaction.coins_amount)).where(
            Transaction.coins_amount > 0
        )
    )
    total_earned = earned_result or 0

    # Всего потрачено
    spent_result = await db.scalar(
        select(func.sum(Transaction.coins_amount)).where(
            Transaction.coins_amount < 0
        )
    )
    total_spent = abs(spent_result or 0)

    # Средний баланс
    avg_balance_result = await db.scalar(
        select(func.avg(User.coins))
    )
    avg_balance = round(avg_balance_result, 0) if avg_balance_result else 0

    # Топ самых богатых
    richest_result = await db.execute(
        select(User.username, User.coins)
        .order_by(desc(User.coins))
        .limit(10)
    )

    richest = [
        {"username": row[0], "coins": row[1]}
        for row in richest_result.all()
    ]

    return {
        "total_coins_in_circulation": int(total_coins),
        "total_coins_earned": int(total_earned),
        "total_coins_spent": int(total_spent),
        "average_user_balance": int(avg_balance),
        "richest_users": richest,
        "economy_health": "healthy" if total_coins > 0 else "needs_seeding"
    }