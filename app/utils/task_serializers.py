"""Utilities for converting Task ORM objects into API responses."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Iterable, List, Sequence

from app.models import Task
from app.schemas import TaskResponse, TaskListResponse
from pydantic import ValidationError

def _normalize_text(
    value: str | None,
    *,
    min_length: int,
    fallback: str,
    max_length: int | None = None,
) -> str:
    """Return a trimmed string that satisfies minimum and maximum lengths."""

    text = (value or "").strip()

    if max_length is not None and text:
        text = text[:max_length].rstrip()

    if len(text) < min_length:
        text = (text or fallback).strip()
        if max_length is not None:
            text = text[:max_length].rstrip()
        if len(text) < min_length:
            text = text.ljust(min_length)
            if max_length is not None and len(text) > max_length:
                text = text[:max_length]

    return text


def _normalize_optional_text(value: object, *, max_length: int) -> str | None:
    """Return a trimmed optional string constrained by max_length."""

    if value is None:
        return None

    text = str(value).strip()
    if not text:
        return None

    if len(text) > max_length:
        text = text[:max_length].rstrip()

    return text or None


def _normalize_task_type(value: object) -> str:
    """Coerce legacy task_type values into a safe, bounded identifier."""

    if value is None:
        normalized = "general"
    else:
        if isinstance(value, str):
            normalized = value.strip()
        else:
            normalized = str(value).strip()
        if not normalized:
            normalized = "general"

    if len(normalized) > 50:
        normalized = normalized[:50].rstrip() or "general"

    return normalized


def _normalize_tags(tags: object) -> list[str]:
    """Return a list of string tags regardless of the stored representation."""
    if not tags:
        return []

    if isinstance(tags, str):
        return [part.strip() for part in tags.split(",") if part.strip()]

    if isinstance(tags, Sequence):
        normalized: list[str] = []
        for tag in tags:
            if tag is None:
                continue
            text = str(tag).strip()
            if text:
                normalized.append(text)
        return normalized

    return []


def _clamp(value: int | None, *, minimum: int, maximum: int | None = None, default: int = 0) -> int:
    """Clamp integer values ensuring sane defaults for nullable DB columns."""
    if value is None:
        value = default

    try:
        coerced = int(value)
    except (TypeError, ValueError):
        coerced = default

    if coerced < minimum:
        coerced = minimum

    if maximum is not None and coerced > maximum:
        coerced = maximum

    return coerced


def _normalize_float(
    value: object,
    *,
    default: float = 0.0,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """Safely convert values to float while respecting optional bounds."""

    result = default

    if value is not None:
        try:
            if isinstance(value, str):
                cleaned = value.strip().replace("%", "")
                if "," in cleaned and "." not in cleaned:
                    cleaned = cleaned.replace(",", ".")
                result = float(cleaned) if cleaned else default
            else:
                result = float(value)
        except (TypeError, ValueError):
            result = default

    if minimum is not None and result < minimum:
        result = minimum

    if maximum is not None and result > maximum:
        result = maximum

    return result

def serialize_task(task: Task) -> TaskResponse:
    """Return a TaskResponse with safe defaults for legacy/nullable columns."""

    title = _normalize_text(
        getattr(task, "title", None),
        min_length=3,
        max_length=200,
        fallback="Без названия",
    )
    description = _normalize_text(
        getattr(task, "description", None),
        min_length=10,
        fallback="Описание будет добавлено позже.",
    )

    task_type = _normalize_task_type(getattr(task, "task_type", None))
    subject = _normalize_optional_text(getattr(task, "subject", None), max_length=50)

    difficulty = _clamp(getattr(task, "difficulty", None), minimum=1, maximum=5, default=1)
    min_level = _clamp(getattr(task, "min_level", None), minimum=1, default=1)
    max_attempts = _clamp(getattr(task, "max_attempts", None), minimum=1, default=1)

    reward_coins = _clamp(getattr(task, "reward_coins", 0), minimum=0, default=0)
    reward_exp = _clamp(getattr(task, "reward_exp", 0), minimum=0, default=0)
    reward_gems = _clamp(getattr(task, "reward_gems", 0), minimum=0, default=0)
    bonus_coins = _clamp(getattr(task, "bonus_coins", 0), minimum=0, default=0)

    time_limit = getattr(task, "time_limit", None)
    if time_limit is not None:
        try:
            time_limit = int(time_limit)
        except (TypeError, ValueError):
            time_limit = None
        else:
            if time_limit <= 0:
                time_limit = None

    created_at = getattr(task, "created_at", None) or getattr(task, "updated_at", None)
    if created_at is None:
        created_at = datetime.utcnow()

    payload = {
        "id": getattr(task, "id", 0),
        "title": title,
        "description": description,
        "task_type": task_type,
        "subject": subject,
        "difficulty": difficulty,
        "content_html": None if getattr(task, "content_html", None) is None else str(getattr(task, "content_html")),
        "topic": _normalize_optional_text(getattr(task, "topic", None), max_length=100),
        "tags": _normalize_tags(getattr(task, "tags", None)),
        "min_level": min_level,
        "time_limit": time_limit,
        "max_attempts": max_attempts,
        "reward_coins": reward_coins,
        "reward_exp": reward_exp,
        "reward_gems": reward_gems,
        "bonus_coins": bonus_coins,
        "image_url": _normalize_optional_text(getattr(task, "image_url", None), max_length=500),
        "video_url": _normalize_optional_text(getattr(task, "video_url", None), max_length=500),
        "is_premium": bool(getattr(task, "is_premium", False)),
        "is_featured": bool(getattr(task, "is_featured", False)),
        "submissions_count": _clamp(getattr(task, "submissions_count", 0), minimum=0, default=0),
        "success_rate": _normalize_float(getattr(task, "success_rate", 0.0), default=0.0, minimum=0.0, maximum=100.0),
        "avg_score": _normalize_float(getattr(task, "avg_score", 0.0), default=0.0, minimum=0.0, maximum=100.0),
        "created_at": created_at,
    }

    try:
        return TaskResponse.model_validate(payload)
    except ValidationError:
        # As a last resort, construct the model without validation to avoid breaking legacy payloads.
        return TaskResponse.model_construct(**payload)

def serialize_tasks(tasks: Iterable[Task]) -> List[TaskResponse]:
    """Serialize a collection of tasks."""
    return [serialize_task(task) for task in tasks]

def build_task_list(tasks: Iterable[Task]) -> TaskListResponse:
    """Вернуть унифицированный ответ со списком заданий."""
    serialized = serialize_tasks(tasks)
    return TaskListResponse(items=serialized, total=len(serialized))