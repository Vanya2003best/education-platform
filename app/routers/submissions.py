"""
API для сдачи работ с загрузкой фотографий
"""
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
import os
import uuid
from datetime import datetime
import json

from app.database import get_db
from app.models import Submission, Task, User, Transaction
from app.services.ai_checker import ai_checker
from app.auth import get_current_user
from app.schemas import SubmissionResponse, SubmissionDetail

router = APIRouter()

# Директория для загрузки фото
UPLOAD_DIR = "uploads/submissions"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Разрешенные форматы
ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.heic'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/submit", response_model=SubmissionResponse)
async def submit_photo_task(
        task_id: int = Form(...),
        photo: UploadFile = File(...),
        background_tasks: BackgroundTasks = None,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Сдать задание - загрузить фото работы

    Процесс:
    1. Сохранить фото
    2. Создать запись о сдаче со статусом "processing"
    3. Запустить AI проверку в фоне
    4. Вернуть ID сдачи
    """

    # Проверяем задание
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Задание не найдено")

    if not task.is_active:
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
        photo_url=f"/uploads/submissions/{unique_filename}",
        photo_filename=unique_filename,
        status="processing"
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

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
    Эта функция запускается асинхронно после загрузки фото
    """
    from app.database import SessionLocal

    db = SessionLocal()

    try:
        # Получаем сдачу
        submission = db.query(Submission).filter(Submission.id == submission_id).first()
        if not submission:
            return

        # Запускаем AI проверку
        result = await ai_checker.check_photo_submission(
            photo_path=file_path,
            task_description=task.description,
            task_type=task.task_type,
            checking_criteria=task.checking_criteria or "{}"
        )

        # Обновляем результаты
        submission.recognized_text = result["recognized_text"]
        submission.score = result["score"]
        submission.ai_feedback = result["feedback"]
        submission.detailed_analysis = json.dumps(result["detailed_analysis"], ensure_ascii=False)
        submission.status = result["status"]
        submission.checked_at = datetime.utcnow()
        submission.processing_time = result["processing_time"]

        # Рассчитываем награды
        coins_earned = calculate_coins(result["score"], task.reward_coins)
        exp_earned = calculate_exp(result["score"], task.reward_exp)

        submission.coins_earned = coins_earned
        submission.exp_earned = exp_earned

        # Обновляем пользователя
        user = db.query(User).filter(User.id == submission.user_id).first()
        if user:
            user.coins += coins_earned
            user.experience += exp_earned
            user.tasks_completed += 1

            # Обновляем средний балл
            total_score = db.query(Submission).filter(
                Submission.user_id == user.id,
                Submission.status == "checked"
            ).count()

            if total_score > 0:
                avg_score = db.query(Submission).filter(
                    Submission.user_id == user.id,
                    Submission.status == "checked"
                ).with_entities(Submission.score).all()
                user.average_score = sum([s[0] for s in avg_score]) / len(avg_score)

            # Проверяем повышение уровня
            new_level = calculate_level(user.experience)
            if new_level > user.level:
                user.level = new_level
                # Можно добавить бонус за новый уровень
                user.coins += 50

        # Создаем транзакцию
        transaction = Transaction(
            user_id=submission.user_id,
            amount=coins_earned,
            transaction_type="task_reward",
            description=f"Награда за задание: {task.title}",
            related_submission_id=submission.id
        )
        db.add(transaction)

        db.commit()

    except Exception as e:
        print(f"Error processing submission {submission_id}: {e}")
        submission.status = "failed"
        submission.ai_feedback = f"Ошибка при обработке: {str(e)}"
        db.commit()

    finally:
        db.close()


@router.get("/my-submissions", response_model=List[SubmissionDetail])
async def get_my_submissions(
        skip: int = 0,
        limit: int = 20,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Получить свои сдачи"""
    submissions = db.query(Submission).filter(
        Submission.user_id == current_user.id
    ).order_by(
        Submission.submitted_at.desc()
    ).offset(skip).limit(limit).all()

    return submissions


@router.get("/{submission_id}", response_model=SubmissionDetail)
async def get_submission(
        submission_id: int,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """Получить детали сдачи"""
    submission = db.query(Submission).filter(
        Submission.id == submission_id
    ).first()

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
        db: Session = Depends(get_db)
):
    """Проверить статус проверки"""
    submission = db.query(Submission).filter(
        Submission.id == submission_id,
        Submission.user_id == current_user.id
    ).first()

    if not submission:
        raise HTTPException(status_code=404, detail="Сдача не найдена")

    return {
        "id": submission.id,
        "status": submission.status,
        "score": submission.score if submission.status == "checked" else None,
        "processing_time": submission.processing_time
    }


def calculate_coins(score: int, base_reward: int) -> int:
    """Рассчитать монеты за оценку"""
    # 100% = полная награда
    # 50% = половина награды
    # 0% = 10% от награды (за попытку)
    multiplier = max(0.1, score / 100)
    return int(base_reward * multiplier)


def calculate_exp(score: int, base_exp: int) -> int:
    """Рассчитать опыт за оценку"""
    multiplier = max(0.3, score / 100)
    return int(base_exp * multiplier)


def calculate_level(experience: int) -> int:
    """Рассчитать уровень по опыту"""
    # Формула: level = sqrt(exp / 100)
    import math
    return max(1, int(math.sqrt(experience / 100)) + 1)