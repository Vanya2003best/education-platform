"""
API для сдачи работ с загрузкой фотографий
"""
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
import os
import uuid
from datetime import datetime
import json

from app.database import get_async_db
from app.models import Submission, Task, User, Transaction, SubmissionStatus
from app.services.ai_checker import ai_checker
from app.auth import get_current_user
from app.schemas import SubmissionResponse, SubmissionDetail

router = APIRouter()

# Директория для загрузки фото
UPLOAD_DIR = "uploads/submissions"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Разрешенные форматы
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.heic', '.webp'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/submit", response_model=SubmissionResponse)
async def submit_photo_task(
        task_id: int = Form(...),
        photo: UploadFile = File(...),
        background_tasks: BackgroundTasks = None,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db)
):
    """
    Сдать задание - загрузить фото работы
    """

    # Проверяем задание
    result = await db.execute(
        select(Task).where(Task.id == task_id)
    )
    task = result.scalar_one_or_none()

    if not task:
        raise HTTPException(status_code=404, detail="Задание не найдено")

    if task.status != "active":
        raise HTTPException(status_code=400, detail="Задание неактивно")

    # Проверяем формат файла
    file_ext = os.path.splitext(photo.filename)[1].lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Неподдерживаемый формат. Разрешены: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Проверяем размер файла
    contents = await photo.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Файл слишком большой (максимум 10 МБ)")

    # Генерируем уникальное имя файла
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    # Сохраняем файл
    with open(file_path, 'wb') as f:
        f.write(contents)

    # Создаем запись о сдаче
    submission = Submission(
        user_id=current_user.id,
        task_id=task.id,
        photo_urls=json.dumps([f"/uploads/submissions/{unique_filename}"]),
        photo_filename=unique_filename,
        status=SubmissionStatus.PROCESSING,
        file_size=len(contents)
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)

    # Запускаем AI проверку в фоновой задаче
    if background_tasks:
        background_tasks.add_task(
            process_submission,
            submission_id=submission.id,
            file_path=file_path,
            task=task
        )

    return {
        "id": submission.id,
        "status": "processing",
        "message": "Фото загружено, началась проверка. Результаты появятся через 10-30 секунд"
    }


async def process_submission(submission_id: int, file_path: str, task: Task):
    """
    Фоновая обработка сдачи - AI проверка
    """
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            # Получаем сдачу
            result = await db.execute(
                select(Submission).where(Submission.id == submission_id)
            )
            submission = result.scalar_one_or_none()
            if not submission:
                return

            # Запускаем AI проверку
            checking_result = await ai_checker.check_photo_submission(
                photo_path=file_path,
                task_description=task.description,
                task_type=task.task_type,
                checking_criteria=json.dumps(task.checking_criteria) if task.checking_criteria else "{}",
                user_id=submission.user_id
            )

            # Обновляем результаты
            submission.recognized_text = checking_result.recognized_text
            submission.score = checking_result.score
            submission.ai_feedback = checking_result.feedback
            submission.detailed_analysis = checking_result.detailed_analysis
            submission.status = SubmissionStatus.CHECKED
            submission.checked_at = datetime.utcnow()
            submission.processing_time = checking_result.processing_time
            submission.confidence_score = checking_result.confidence_score

            # Рассчитываем награды
            coins_earned = calculate_coins(checking_result.score, task.reward_coins)
            exp_earned = calculate_exp(checking_result.score, task.reward_exp)

            submission.coins_earned = coins_earned
            submission.exp_earned = exp_earned

            # Обновляем пользователя
            user_result = await db.execute(
                select(User).where(User.id == submission.user_id)
            )
            user = user_result.scalar_one_or_none()

            if user:
                user.coins += coins_earned
                user.experience += exp_earned
                user.tasks_completed += 1

                # Обновляем средний балл
                submissions_result = await db.execute(
                    select(Submission)
                    .where(
                        Submission.user_id == user.id,
                        Submission.status == SubmissionStatus.CHECKED
                    )
                )
                all_submissions = submissions_result.scalars().all()

                if all_submissions:
                    avg_score = sum(s.score for s in all_submissions) / len(all_submissions)
                    user.average_score = avg_score
                    user.best_score = max(s.score for s in all_submissions)

                # Проверяем повышение уровня
                new_level = calculate_level(user.experience)
                if new_level > user.level:
                    user.level = new_level
                    user.coins += 50  # Бонус за новый уровень

            # Создаем транзакцию
            transaction = Transaction(
                user_id=submission.user_id,
                coins_amount=coins_earned,
                exp_amount=exp_earned,
                transaction_type="task_reward",
                category="reward",
                description=f"Награда за задание: {task.title}",
                related_submission_id=submission.id,
                coins_balance=user.coins if user else 0
            )
            db.add(transaction)

            await db.commit()

        except Exception as e:
            print(f"Error processing submission {submission_id}: {e}")
            submission.status = SubmissionStatus.FAILED
            submission.ai_feedback = f"Ошибка при обработке: {str(e)}"
            await db.commit()


@router.get("/my-submissions", response_model=List[SubmissionDetail])
async def get_my_submissions(
        skip: int = 0,
        limit: int = 20,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db)
):
    """Получить свои сдачи"""
    result = await db.execute(
        select(Submission)
        .where(Submission.user_id == current_user.id)
        .order_by(Submission.submitted_at.desc())
        .offset(skip)
        .limit(limit)
    )
    submissions = result.scalars().all()

    return submissions


@router.get("/{submission_id}", response_model=SubmissionDetail)
async def get_submission(
        submission_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db)
):
    """Получить детали сдачи"""
    result = await db.execute(
        select(Submission).where(Submission.id == submission_id)
    )
    submission = result.scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="Сдача не найдена")

    # Проверяем права доступа
    if submission.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Нет доступа")

    return submission


@router.get("/{submission_id}/status")
async def get_submission_status(
        submission_id: int,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db)
):
    """Проверить статус проверки"""
    result = await db.execute(
        select(Submission).where(
            Submission.id == submission_id,
            Submission.user_id == current_user.id
        )
    )
    submission = result.scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="Сдача не найдена")

    return {
        "id": submission.id,
        "status": submission.status.value if hasattr(submission.status, 'value') else submission.status,
        "score": submission.score if submission.status == SubmissionStatus.CHECKED else None,
        "processing_time": submission.processing_time
    }


def calculate_coins(score: float, base_reward: int) -> int:
    """Рассчитать монеты за оценку"""
    multiplier = max(0.1, score / 100)
    return int(base_reward * multiplier)


def calculate_exp(score: float, base_exp: int) -> int:
    """Рассчитать опыт за оценку"""
    multiplier = max(0.3, score / 100)
    return int(base_exp * multiplier)


def calculate_level(experience: int) -> int:
    """Рассчитать уровень по опыту"""
    import math
    return max(1, int(math.sqrt(experience / 100)) + 1)