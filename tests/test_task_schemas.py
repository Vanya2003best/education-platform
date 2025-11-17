"""Tests for flexible task type handling in task schemas."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys

# Ensure the application package is importable when tests are run directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dataclasses import dataclass, replace

import pytest

from app.schemas import TaskCreate, TaskResponse
from app.utils.task_serializers import serialize_task


@dataclass
class DummyTask:
    id: int = 1
    title: str | None = "T"
    description: str | None = "Too short"
    task_type: str | None = " custom_type "
    subject: str | None = None
    difficulty: int | None = 0
    content_html: str | None = None
    topic: str | None = None
    tags: object = "math, algebra , ,"
    min_level: int | None = 0
    time_limit: object = -5
    max_attempts: int | None = 0
    reward_coins: object = "15"
    reward_exp: object = None
    reward_gems: object = -3
    bonus_coins: object = "not-a-number"
    image_url: str | None = None
    video_url: str | None = None
    is_premium: bool | None = None
    is_featured: bool | None = None
    submissions_count: object = -10
    success_rate: object = "0.75"
    avg_score: object = None
    created_at: None = None
    updated_at: None = None
    assignments: object = None

@dataclass
class DummyAssignment:
    user_id: int
    assigned_at: datetime | None = None
    is_completed: bool | None = None
    completed_at: datetime | None = None
    user: object | None = None

@dataclass
class DummyUser:
    id: int
    username: str | None = None
    email: str | None = None


def test_task_create_accepts_custom_task_type():
    payload = {
        "title": "New creative task",
        "description": "Write a short story about innovation.",
        "task_type": "creative_writing",
        "difficulty": 3,
    }

    task = TaskCreate(**payload)
    assert task.task_type == "creative_writing"


def test_task_response_handles_unknown_task_type():
    payload = {
        "id": 1,
        "title": "Physics challenge",
        "description": "Solve the riddle.",
        "task_type": "astro_physics",
        "subject": "Physics",
        "difficulty": 4,
        "content_html": None,
        "topic": None,
        "tags": [],
        "min_level": 1,
        "time_limit": None,
        "max_attempts": 3,
        "reward_coins": 10,
        "reward_exp": 20,
        "reward_gems": 0,
        "bonus_coins": 0,
        "image_url": None,
        "video_url": None,
        "is_premium": False,
        "is_featured": False,
        "submissions_count": 0,
        "success_rate": 0.0,
        "avg_score": 0.0,
        "created_at": datetime.utcnow(),
    }

    response = TaskResponse.model_validate(payload)
    assert response.task_type == "astro_physics"


def test_task_response_falls_back_to_general_for_missing_type():
    payload = {
        "id": 2,
        "title": "Legacy task",
        "description": "Old task without type.",
        "task_type": None,
        "subject": None,
        "difficulty": 2,
        "content_html": None,
        "topic": None,
        "tags": [],
        "min_level": 1,
        "time_limit": None,
        "max_attempts": 3,
        "reward_coins": 5,
        "reward_exp": 10,
        "reward_gems": 0,
        "bonus_coins": 0,
        "image_url": None,
        "video_url": None,
        "is_premium": False,
        "is_featured": False,
        "submissions_count": 0,
        "success_rate": 0.0,
        "avg_score": 0.0,
        "created_at": datetime.utcnow(),
    }

    response = TaskResponse.model_validate(payload)
    assert response.task_type == "general"


def test_task_response_coerces_non_string_type():
    payload = {
        "id": 3,
        "title": "Numeric type",
        "description": "Task with numeric type.",
        "task_type": 1234,
        "subject": None,
        "difficulty": 1,
        "content_html": None,
        "topic": None,
        "tags": [],
        "min_level": 1,
        "time_limit": None,
        "max_attempts": 1,
        "reward_coins": 1,
        "reward_exp": 1,
        "reward_gems": 0,
        "bonus_coins": 0,
        "image_url": None,
        "video_url": None,
        "is_premium": False,
        "is_featured": False,
        "submissions_count": 0,
        "success_rate": 0.0,
        "avg_score": 0.0,
        "created_at": datetime.utcnow(),
    }

    response = TaskResponse.model_validate(payload)
    assert response.task_type == "1234"


def test_serialize_task_normalizes_legacy_records():
    task = DummyTask()

    serialized = serialize_task(task)

    assert serialized.title == "T  "  # padded to minimum length 3
    assert serialized.description.startswith("Too short")
    assert len(serialized.description) >= 10
    assert serialized.task_type == "custom_type"
    assert serialized.difficulty == 1
    assert serialized.min_level == 1
    assert serialized.max_attempts == 1
    assert serialized.reward_coins == 15
    assert serialized.reward_exp == 0
    assert serialized.reward_gems == 0
    assert serialized.bonus_coins == 0
    assert serialized.tags == ["math", "algebra"]
    assert serialized.time_limit is None
    assert serialized.submissions_count == 0
    assert serialized.success_rate == 0.75
    assert serialized.created_at is not None


def test_serialize_task_truncates_subject_and_percentages():
    long_subject = "   Advanced Mathematics and Problem Solving for Olympiad Training   "
    long_type = "experimental-project-based-learning-for-upper-grade-students"
    task = replace(
        DummyTask(),
        subject=long_subject,
        task_type=long_type,
        success_rate="87.5%",
        avg_score="91,5",
    )

    serialized = serialize_task(task)

    assert serialized.subject is not None
    assert len(serialized.subject) <= 50
    assert serialized.subject.startswith("Advanced Mathematics")
    assert len(serialized.task_type) <= 50
    assert serialized.success_rate == pytest.approx(87.5)
    assert serialized.avg_score == pytest.approx(91.5)

def test_serialize_task_includes_assignments_when_prefetched():
    user = DummyUser(id=7, username="alice", email="alice@example.com")
    assignment = DummyAssignment(
        user_id=7,
        assigned_at=datetime(2024, 1, 1, 12, 0, 0),
        is_completed=True,
        completed_at=datetime(2024, 1, 2, 15, 30, 0),
        user=user,
    )
    task = DummyTask(assignments=[assignment])

    serialized = serialize_task(task)

    assert serialized.assigned_users, "Expected assignment info in payload"
    first_assignment = serialized.assigned_users[0]
    assert first_assignment.id == 7
    assert first_assignment.username == "alice"
    assert first_assignment.email == "alice@example.com"
    assert first_assignment.is_completed is True