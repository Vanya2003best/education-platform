from __future__ import annotations

from datetime import datetime
from typing import Any
import sys
import types

from app.models import TaskStatus


def ensure_optional_deps_stubbed() -> None:
    """Register lightweight stubs for optional heavy dependencies."""
    cv2_stub = types.SimpleNamespace(
        imread=lambda *args, **kwargs: None,
        cvtColor=lambda *args, **kwargs: None,
        fastNlMeansDenoising=lambda *args, **kwargs: None,
        adaptiveThreshold=lambda *args, **kwargs: None,
        morphologyEx=lambda *args, **kwargs: None,
        minAreaRect=lambda coords: (None, None, 0),
        getRotationMatrix2D=lambda *args, **kwargs: None,
        warpAffine=lambda *args, **kwargs: None,
        COLOR_BGR2GRAY=0,
        ADAPTIVE_THRESH_GAUSSIAN_C=0,
        THRESH_BINARY=0,
        MORPH_CLOSE=0,
        INTER_CUBIC=0,
        BORDER_REPLICATE=0,
        ml=types.SimpleNamespace(),
    )
    pytesseract_stub = types.SimpleNamespace(image_to_string=lambda *args, **kwargs: "")
    openai_stub = types.SimpleNamespace(AsyncOpenAI=lambda *args, **kwargs: None)

    sys.modules.setdefault("cv2", cv2_stub)
    sys.modules.setdefault("pytesseract", pytesseract_stub)
    sys.modules.setdefault("openai", openai_stub)


class DummyTask:
    def __init__(self) -> None:
        self.id = 42
        self.title = " Legacy Title"
        self.description = "Short"
        self.task_type = "  experimental-category "
        self.subject = "Advanced Astrophysics for Secondary School Students"
        self.difficulty = 6
        self.content_html = {"note": "rich"}
        self.topic = "  Deep Space Exploration Technologies and Engineering Principles  "
        self.tags = ["science", None, " research "]
        self.min_level = 0
        self.time_limit = "45"
        self.max_attempts = 0
        self.reward_coins = "150"
        self.reward_exp = "250"
        self.reward_gems = "10"
        self.bonus_coins = "5"
        self.image_url = "   https://example.com/image.png   "
        self.video_url = None
        self.is_premium = 1
        self.is_featured = None
        self.submissions_count = "-5"
        self.success_rate = "92%"
        self.avg_score = "88,75"
        self.created_at = None
        self.updated_at = datetime(2024, 1, 1, 12, 0, 0)
        self.status = TaskStatus.ACTIVE
        self.is_admin_task = True
        self.assignments = []


class DummyResult:
    def __init__(self, tasks: list[Any]) -> None:
        self._tasks = tasks

    def scalars(self) -> DummyResult:
        return self

    def scalar_one(self) -> int:
        return len(self._tasks)

    def scalar(self) -> int:
        return len(self._tasks)

    def first(self) -> tuple[int]:
        return (len(self._tasks),)

    def all(self) -> list[Any]:
        return self._tasks

    def scalar_one_or_none(self) -> Any | None:
        if not self._tasks:
            return None
        if len(self._tasks) == 1:
            return self._tasks[0]
        raise RuntimeError("DummyResult.scalar_one_or_none only supports up to one task")


class DummySession:
    def __init__(self, tasks: list[DummyTask]) -> None:
        self._tasks: list[Any] = list(tasks)
        existing_ids = [getattr(task, "id", 0) for task in self._tasks]
        self._next_id = (max(existing_ids) if existing_ids else 0) + 1

    def _find_task(self, task_id: int) -> Any | None:
        for task in self._tasks:
            if getattr(task, "id", None) == task_id:
                return task
        return None

    def _resolve_bound_value(self, expression: Any) -> Any:
        from sqlalchemy.sql.elements import BindParameter

        if expression is None:
            return None
        if isinstance(expression, BindParameter):
            return expression.value
        if hasattr(expression, "value"):
            return getattr(expression, "value")
        nested = getattr(expression, "element", None)
        if nested is expression:
            return None
        if nested is not None:
            return self._resolve_bound_value(nested)
        return None

    def _filter_tasks(self, statement: Any) -> list[Any]:
        from sqlalchemy.sql import Select
        from sqlalchemy.sql.elements import BinaryExpression
        from sqlalchemy.sql import operators as sql_operators

        if not isinstance(statement, Select):
            return list(self._tasks)

        filtered = list(self._tasks)
        for criterion in getattr(statement, "_where_criteria", ()):  # type: ignore[attr-defined]
            if not isinstance(criterion, BinaryExpression):
                continue
            left = getattr(criterion, "left", None)
            operator = getattr(criterion, "operator", None)
            if getattr(left, "key", None) != "id" or operator is not sql_operators.eq:
                continue
            value = self._resolve_bound_value(getattr(criterion, "right", None))
            if value is None:
                continue
            filtered = [task for task in filtered if getattr(task, "id", None) == value]
        return filtered

    async def execute(self, *args: Any, **kwargs: Any) -> DummyResult:
        statement = args[0] if args else None
        return DummyResult(self._filter_tasks(statement))

    def add(self, obj: Any) -> None:
        if getattr(obj, "id", None) in (None, 0):
            setattr(obj, "id", self._next_id)
            self._next_id += 1
        self._tasks.append(obj)

    def add_all(self, objects: list[Any]) -> None:
        for obj in objects:
            self.add(obj)

    async def delete(self, obj: Any) -> None:
        self._tasks = [task for task in self._tasks if task is not obj]

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def flush(self) -> None:
        return None

    async def refresh(self, obj: Any) -> None:
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.utcnow()
        if getattr(obj, "updated_at", None) is None:
            obj.updated_at = obj.created_at
        defaults = {
            "status": TaskStatus.ACTIVE,
            "submissions_count": 0,
            "success_rate": 0.0,
            "avg_score": 0.0,
            "reward_gems": getattr(obj, "reward_gems", 0) or 0,
            "bonus_coins": getattr(obj, "bonus_coins", 0) or 0,
            "is_premium": getattr(obj, "is_premium", False) or False,
            "is_featured": getattr(obj, "is_featured", False) or False,
        }
        for field_name, default_value in defaults.items():
            if getattr(obj, field_name, None) is None:
                setattr(obj, field_name, default_value)

    def list_tasks(self) -> list[Any]:
        return list(self._tasks)


__all__ = [
    "DummySession",
    "DummyTask",
    "ensure_optional_deps_stubbed",
]