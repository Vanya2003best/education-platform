from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Iterator
import types
import sys

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Stub heavy optional dependencies before importing the app
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

from app.main import app  # noqa: E402  # import after stubbing optional deps
import app.main as app_main  # noqa: E402
from app.auth import require_admin
from app.database import get_async_db
from app.models import TaskStatus
from app.utils.task_serializers import serialize_task


class DummyTask:
    def __init__(self) -> None:
        self.id = 42
        self.title = " Legacy Title"
        self.description = "Short"
        self.task_type = "  experimental-category "
        self.subject = "Advanced Astrophysics for Secondary School Students"
        self.difficulty = 6  # outside normal range to test clamping
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


class DummyResult:
    def __init__(self, tasks: list[Any]) -> None:
        self._tasks = tasks

    def scalars(self) -> "DummyResult":
        return self

    def scalar_one(self) -> int:
        return len(self._tasks)

    def scalar(self) -> int:
        return len(self._tasks)

    def first(self) -> tuple[int]:
        return (len(self._tasks),)

    def all(self) -> list[Any]:
        return self._tasks


class DummySession:
    def __init__(self, tasks: list[DummyTask]) -> None:
        self._tasks: list[Any] = list(tasks)
        existing_ids = [getattr(task, "id", 0) for task in self._tasks]
        self._next_id = (max(existing_ids) if existing_ids else 0) + 1

    async def execute(self, *args: Any, **kwargs: Any) -> DummyResult:
        return DummyResult(self._tasks)

    def add(self, obj: Any) -> None:
        if getattr(obj, "id", None) in (None, 0):
            setattr(obj, "id", self._next_id)
            self._next_id += 1
        self._tasks.append(obj)

    def add_all(self, objects: list[Any]) -> None:  # pragma: no cover - compatibility
        for obj in objects:
            self.add(obj)

    async def commit(self) -> None:  # pragma: no cover - API compatibility
        return None

    async def rollback(self) -> None:  # pragma: no cover - API compatibility
        return None

    async def close(self) -> None:  # pragma: no cover - API compatibility
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
        for key, value in defaults.items():
            if getattr(obj, key, None) is None:
                setattr(obj, key, value)


@pytest.fixture
def client() -> Iterator[TestClient]:
    async def override_db() -> AsyncIterator[DummySession]:
        yield DummySession([DummyTask()])

    def override_admin() -> Any:
        return types.SimpleNamespace(id=1, role="admin")

    app.dependency_overrides[get_async_db] = override_db
    app.dependency_overrides[require_admin] = override_admin

    original_init_db = app_main.init_db
    original_close_db = app_main.close_db
    original_connect = app_main.cache_manager.connect
    original_disconnect = app_main.cache_manager.disconnect
    original_is_connected = app_main.cache_manager.is_connected
    original_invalidate = app_main.cache_manager.invalidate_pattern

    app_main.init_db = AsyncMock()
    app_main.close_db = AsyncMock()
    app_main.cache_manager.connect = AsyncMock()
    app_main.cache_manager.disconnect = AsyncMock()
    app_main.cache_manager.is_connected = lambda: False
    app_main.cache_manager.invalidate_pattern = AsyncMock()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.pop(get_async_db, None)
    app.dependency_overrides.pop(require_admin, None)
    app_main.init_db = original_init_db
    app_main.close_db = original_close_db
    app_main.cache_manager.connect = original_connect
    app_main.cache_manager.disconnect = original_disconnect
    app_main.cache_manager.is_connected = original_is_connected
    app_main.cache_manager.invalidate_pattern = original_invalidate


def test_admin_tasks_endpoint_returns_sanitized_payload(client: TestClient) -> None:
    response = client.get("/api/admin/tasks", headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    assert response.headers.get("X-Total-Count") == "1"
    data = response.json()
    assert isinstance(data, list)
    assert data, "Expected at least one task in response"

    task = data[0]
    assert task["title"].startswith("Legacy Title")
    assert task["description"].startswith("Short")
    assert task["task_type"].startswith("experimental-category")
    assert len(task["task_type"]) <= 50
    assert len(task["subject"]) <= 50
    assert task["difficulty"] == 5  # clamped maximum
    assert task["min_level"] == 1
    assert task["max_attempts"] == 1
    assert task["reward_coins"] == 150
    assert task["reward_exp"] == 250
    assert task["reward_gems"] == 10
    assert task["bonus_coins"] == 5
    assert task["tags"] == ["science", "research"]
    assert task["time_limit"] == 45
    assert task["submissions_count"] == 0
    assert task["success_rate"] == pytest.approx(92.0)
    assert task["avg_score"] == pytest.approx(88.75)
    assert task["created_at"] is not None


def test_public_tasks_endpoint_uses_same_serializer(client: TestClient) -> None:
    response = client.get("/api/tasks/")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, list)
    assert data
    # Ensure the serializer behaviour matches direct invocation
    serialized = serialize_task(DummyTask())
    assert data[0]["task_type"] == serialized.task_type
    assert data[0]["subject"] == serialized.subject
    assert data[0]["status"] == serialized.status

    def test_admin_tasks_preflight_options_request(client: TestClient) -> None:
        response = client.options(
            "/api/admin/tasks",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization, content-type",
            },
        )
        assert response.status_code in (200, 204)
        headers = {k.lower(): v for k, v in response.headers.items()}
        allow_methods = headers.get("access-control-allow-methods", "")
        assert "post" in allow_methods.lower(), allow_methods

    def test_create_admin_task_accepts_complete_payload(client: TestClient) -> None:
        payload = {
            "title": "Практическое задание №1",
            "description": "Сделайте то-то и приложите решение.",
            "task_type": "essay",
            "subject": "Русский язык",
            "difficulty": 2,
            "reward_coins": 20,
            "reward_exp": 100,
            "min_level": 1,
            "max_attempts": 3,
            "time_limit": None,
            "content_html": "<h2>Практическое задание</h2>",
            "assigned_user_ids": [],
        }

        response = client.post(
            "/api/admin/tasks",
            headers={"Authorization": "Bearer token"},
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == payload["title"]
        assert data["content_html"] == payload["content_html"]
        assert data["difficulty"] == payload["difficulty"]
        assert data["reward_coins"] == payload["reward_coins"]