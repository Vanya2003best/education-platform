"""Utilities for converting Task ORM objects into API responses."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, List

from app.models import Task
from app.schemas import TaskResponse


def serialize_task(task: Task) -> TaskResponse:
    """Return a TaskResponse with safe defaults for nullable columns."""
    return TaskResponse(
        id=task.id,
        title=task.title,
        description=task.description,
        task_type=task.task_type,
        subject=task.subject,
        difficulty=task.difficulty or 1,
        content_html=task.content_html,
        topic=getattr(task, "topic", None),
        tags=task.tags or [],
        min_level=task.min_level or 1,
        time_limit=getattr(task, "time_limit", None),
        max_attempts=task.max_attempts or 1,
        reward_coins=task.reward_coins or 0,
        reward_exp=task.reward_exp or 0,
        reward_gems=task.reward_gems or 0,
        bonus_coins=task.bonus_coins or 0,
        image_url=getattr(task, "image_url", None),
        video_url=getattr(task, "video_url", None),
        is_premium=bool(task.is_premium),
        is_featured=bool(task.is_featured),
        submissions_count=task.submissions_count or 0,
        success_rate=float(task.success_rate or 0.0),
        avg_score=float(task.avg_score or 0.0),
        created_at=task.created_at or datetime.utcnow(),
    )


def serialize_tasks(tasks: Iterable[Task]) -> List[TaskResponse]:
    """Serialize a collection of tasks."""
    return [serialize_task(task) for task in tasks]