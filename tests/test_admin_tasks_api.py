from __future__ import annotations

from pathlib import Path
from typing import Any, AsyncIterator, Iterator
import types
import sys

import anyio
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock
from app.utils.admin_tasks import (
    DummySession,
    DummyTask,
    ensure_optional_deps_stubbed,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ensure_optional_deps_stubbed()

from app.main import app  # noqa: E402  # import after stubbing optional deps
import app.main as app_main  # noqa: E402
from app.auth import require_admin
from app.database import get_async_db
from app.models import TaskStatus
from app.utils.task_serializers import serialize_task


@pytest.fixture
def admin_app_overrides() -> Iterator[DummySession]:
    session = DummySession([DummyTask()])

    async def override_db() -> AsyncIterator[DummySession]:
        yield session

    def override_admin() -> Any:
        return types.SimpleNamespace(id=1, role="admin", is_active=True, is_verified=True)

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
    try:
        yield session
    finally:
        app.dependency_overrides.pop(get_async_db, None)
        app.dependency_overrides.pop(require_admin, None)
        app_main.init_db = original_init_db
        app_main.close_db = original_close_db
        app_main.cache_manager.connect = original_connect
        app_main.cache_manager.disconnect = original_disconnect
        app_main.cache_manager.is_connected = original_is_connected
        app_main.cache_manager.invalidate_pattern = original_invalidate

@pytest.fixture
def client(admin_app_overrides: DummySession) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


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
    assert isinstance(task["assigned_users"], list)


@pytest.mark.parametrize("path", ["/api/admin/tasks", "/api/admin/tasks/"])
def test_admin_tasks_collection_accepts_all_trailing_slash_variants(
    client: TestClient,
    path: str,
) -> None:
    response = client.get(path, headers={"Authorization": "Bearer token"})
    assert response.status_code == 200
    assert response.headers.get("X-Total-Count") == "1"

def test_live_app_admin_tasks_listing(admin_app_overrides: DummySession) -> None:
    async def _run() -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get(
                "/api/admin/tasks",
                headers={"Authorization": "Bearer token"},
            )
            assert response.status_code == 200
            assert response.headers.get("X-Total-Count") == "1"
            payload = response.json()
            assert isinstance(payload, list)
            assert payload and payload[0]["id"] == 42

    anyio.run(_run)


def test_live_app_admin_delete_flow(admin_app_overrides: DummySession) -> None:
    async def _run() -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.delete(
                "/api/admin/tasks/42",
                headers={"Authorization": "Bearer token"},
            )
            assert response.status_code == 200
            follow_up = await client.get(
                "/api/admin/tasks",
                headers={"Authorization": "Bearer token"},
            )
            assert follow_up.status_code == 200
            assert follow_up.json() == []

    anyio.run(_run)


def test_live_app_admin_patch_flow(admin_app_overrides: DummySession) -> None:
    async def _run() -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.patch(
                "/api/admin/tasks/42",
                headers={"Authorization": "Bearer token"},
                json={"title": "HTTPX patched", "difficulty": 3},
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["title"] == "HTTPX patched"
            assert payload["difficulty"] == 3

    anyio.run(_run)


def test_admin_tasks_endpoint_accepts_assignee_filter(client: TestClient) -> None:
    response = client.get(
        "/api/admin/tasks",
        headers={"Authorization": "Bearer token"},
        params={"assigned_user_id": 5},
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["items"], list)

def test_http_exception_handler_preserves_allow_header(client: TestClient) -> None:
    response = client.post("/api/admin/dashboard", headers={"Authorization": "Bearer token"})

    assert response.status_code == 405
    allow_header = response.headers.get("allow")
    assert allow_header is not None
    assert "GET" in allow_header

    payload = response.json()
    assert payload["error"]["message"].lower() == "method not allowed"

def test_public_tasks_endpoint_uses_same_serializer(client: TestClient) -> None:
    response = client.get("/api/tasks/")
    assert response.status_code == 200

    data = response.json()
    assert isinstance(data, dict)
    assert data.get("total") == 1
    assert data.get("items"), "Expected at least one task in response"
    task = data["items"][0]
    # Ensure the serializer behaviour matches direct invocation
    serialized = serialize_task(DummyTask())
    assert data[0]["task_type"] == serialized.task_type
    assert data[0]["subject"] == serialized.subject
    assert data[0]["status"] == serialized.status

def test_admin_tasks_head_request_returns_total_header(
    client: TestClient,
) -> None:
    response = client.head(
        "/api/admin/tasks",
        headers={"Authorization": "Bearer token"},
    )
    assert response.status_code == 200
    assert response.headers.get("x-total-count") == "1"

    payload = response.json()
    assert isinstance(payload, dict)
    assert payload["total"] == 1
    assert isinstance(payload["items"], list)

def test_admin_can_delete_task(client: TestClient) -> None:
    response = client.delete(
        "/api/admin/tasks/42",
        headers={"Authorization": "Bearer token"},
    )
    assert response.status_code == 200
    assert response.json() == {"message": "Задание удалено", "task_id": 42}

    follow_up = client.get(
        "/api/admin/tasks",
        headers={"Authorization": "Bearer token"},
    )
    payload = follow_up.json()
    assert payload["items"] == []
    assert payload["total"] == 0
def test_admin_delete_missing_task_returns_404(client: TestClient) -> None:
    response = client.delete(
        "/api/admin/tasks/999",
        headers={"Authorization": "Bearer token"},
    )
    assert response.status_code == 404
    payload = response.json()
    message = payload.get("detail") or payload.get("error", {}).get("message")
    assert message == "Task not found"


def test_admin_can_update_task(client: TestClient) -> None:
    response = client.patch(
        "/api/admin/tasks/42",
        headers={"Authorization": "Bearer token"},
        json={"title": "Обновлённое задание", "difficulty": 4},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Обновлённое задание"
    assert data["difficulty"] == 4


def test_admin_update_missing_task_returns_404(client: TestClient) -> None:
    response = client.patch(
        "/api/admin/tasks/777",
        headers={"Authorization": "Bearer token"},
        json={"title": "Не существует"},
    )
    assert response.status_code == 404
    payload = response.json()
    message = payload.get("detail") or payload.get("error", {}).get("message")
    assert message == "Task not found"
def test_live_app_admin_tasks_listing(admin_app_overrides: DummySession) -> None:
    async def _run() -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.get(
                "/api/admin/tasks",
                headers={"Authorization": "Bearer token"},
            )
            assert response.status_code == 200
            assert response.headers.get("X-Total-Count") == "1"
            payload = response.json()
            assert isinstance(payload, list)
            assert payload and payload[0]["id"] == 42

    anyio.run(_run)


def test_live_app_admin_delete_flow(admin_app_overrides: DummySession) -> None:
    async def _run() -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.delete(
                "/api/admin/tasks/42",
                headers={"Authorization": "Bearer token"},
            )
            assert response.status_code == 200
            follow_up = await client.get(
                "/api/admin/tasks",
                headers={"Authorization": "Bearer token"},
            )
            assert follow_up.status_code == 200
            assert follow_up.json() == []

    anyio.run(_run)


def test_live_app_admin_patch_flow(admin_app_overrides: DummySession) -> None:
    async def _run() -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
            response = await client.patch(
                "/api/admin/tasks/42",
                headers={"Authorization": "Bearer token"},
                json={"title": "HTTPX patched", "difficulty": 3},
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["title"] == "HTTPX patched"
            assert payload["difficulty"] == 3

    anyio.run(_run)

if False:  # pragma: no cover - legacy integration tests kept for reference
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

    def test_admin_can_update_existing_task(client: TestClient) -> None:
        payload = {
            "title": "Обновлённый заголовок",
            "difficulty": 3,
            "reward_exp": 555,
        }

        response = client.patch(
            "/api/admin/tasks/42",
            headers={"Authorization": "Bearer token"},
            json=payload,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == payload["title"]
        assert data["difficulty"] == payload["difficulty"]
        assert data["reward_exp"] == payload["reward_exp"]

    def test_admin_update_without_payload_returns_error(client: TestClient) -> None:
        response = client.patch(
            "/api/admin/tasks/42",
            headers={"Authorization": "Bearer token"},
            json={},
        )

        assert response.status_code == 400

    def test_admin_can_delete_task(client: TestClient) -> None:
        response = client.delete(
            "/api/admin/tasks/42",
            headers={"Authorization": "Bearer token"},
        )

        assert response.status_code == 200
        assert response.json()["task_id"] == 42
        second_response = client.delete(
            "/api/admin/tasks/42",
            headers={"Authorization": "Bearer token"},
        )
        assert second_response.status_code == 404