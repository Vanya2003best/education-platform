from __future__ import annotations

import asyncio
import sys
import types
from typing import AsyncGenerator

import pytest
for optional in ("cv2", "pytesseract"):
    if optional not in sys.modules:
        sys.modules[optional] = types.ModuleType(optional)

from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_async_db
from app.models import Base, Task, User, UserRole, TaskAssignment, TaskStatus
from app.auth import get_current_user, require_admin
from app.routers import tasks as tasks_router
from app.routers import admin as admin_router

engine = create_engine(
    "sqlite:///:memory:",
    future=True,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

api_app = FastAPI()
api_app.include_router(tasks_router.router, prefix="/api/tasks")
api_app.include_router(admin_router.router, prefix="/api/admin")


class AsyncSessionWrapper:
    def __init__(self, session):
        self._session = session

    def add(self, instance):
        self._session.add(instance)

    def add_all(self, instances):
        self._session.add_all(instances)

    async def execute(self, statement):
        return await asyncio.to_thread(self._session.execute, statement)

    async def scalar(self, statement):
        return await asyncio.to_thread(self._session.scalar, statement)

    async def commit(self):
        await asyncio.to_thread(self._session.commit)

    async def flush(self):
        await asyncio.to_thread(self._session.flush)

    async def refresh(self, instance):
        await asyncio.to_thread(self._session.refresh, instance)

    async def rollback(self):
        await asyncio.to_thread(self._session.rollback)

    async def close(self):
        await asyncio.to_thread(self._session.close)


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def override_dependencies():
    async def _get_db():
        wrapper = AsyncSessionWrapper(SessionLocal())
        try:
            yield wrapper
            await wrapper.commit()
        finally:
            await wrapper.close()

    api_app.dependency_overrides[get_async_db] = _get_db
    yield
    api_app.dependency_overrides.pop(get_async_db, None)
    api_app.dependency_overrides.pop(get_current_user, None)
    api_app.dependency_overrides.pop(require_admin, None)


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def async_client():
    transport = ASGITransport(app=api_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def seeded_users():
    session = SessionLocal()
    try:
        await asyncio.to_thread(session.execute, delete(TaskAssignment))
        await asyncio.to_thread(session.execute, delete(Task))
        await asyncio.to_thread(session.execute, delete(User))
        admin = User(
            username="admin",
            email="admin@example.com",
            password_hash="hashed",
            role=UserRole.ADMIN,
            is_active=True,
        )
        student = User(
            username="student",
            email="student@example.com",
            password_hash="hashed",
            role=UserRole.STUDENT,
            is_active=True,
        )
        session.add_all([admin, student])
        await asyncio.to_thread(session.commit)
        return {"admin": admin, "student": student}
    finally:
        await asyncio.to_thread(session.close)


@pytest.mark.anyio
async def test_public_task_list_returns_items(async_client, seeded_users):
    session = SessionLocal()
    try:
        await asyncio.to_thread(session.execute, delete(Task))
        session.add_all([
            Task(
                title="Задание 1",
                description="Описание задания номер один",
                task_type="math",
                status=TaskStatus.ACTIVE,
                is_admin_task=True,
            ),
            Task(
                title="Задание 2",
                description="Описание задания номер два",
                task_type="math",
                status=TaskStatus.ACTIVE,
            ),
            Task(
                title="Черновик",
                description="Черновик задания для теста",
                task_type="math",
                status=TaskStatus.ARCHIVED,
            ),
        ])
        await asyncio.to_thread(session.commit)
    finally:
        await asyncio.to_thread(session.close)

    response = await async_client.get("/api/tasks")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert all("id" in item for item in payload["items"])
    assert all(item["status"] == "active" for item in payload["items"])

@pytest.mark.anyio
async def test_admin_task_listing_requires_admin(async_client, seeded_users):
    admin_user = seeded_users["admin"]

    async def override_admin():
        return admin_user

    api_app.dependency_overrides[require_admin] = override_admin

    session = SessionLocal()
    try:
        await asyncio.to_thread(session.execute, delete(Task))
        session.add_all([
            Task(
                title="Admin Task",
                description="Admin created task for listing",
                task_type="math",
                status=TaskStatus.ACTIVE,
                is_admin_task=True,
            ),
            Task(
                title="Teacher Task",
                description="Teacher created task also needs admin visibility",
                task_type="math",
                status=TaskStatus.ACTIVE,
            ),
        ])
        await asyncio.to_thread(session.commit)
    finally:
        await asyncio.to_thread(session.close)

    response = await async_client.get("/api/admin/tasks")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    titles = {item["title"] for item in data["items"]}
    assert {"Admin Task", "Teacher Task"} <= titles


@pytest.mark.anyio
async def test_admin_create_task_persists(async_client, seeded_users):
    admin_user = seeded_users["admin"]

    async def override_admin():
        return admin_user

    api_app.dependency_overrides[require_admin] = override_admin

    payload = {
        "title": "Новое задание",
        "description": "Подробное описание задания",
        "task_type": "math",
        "difficulty": 2,
        "min_level": 1,
        "max_attempts": 3,
        "reward_coins": 10,
        "reward_exp": 50,
    }

    response = await async_client.post(
        "/api/admin/tasks",
        json=payload,
        headers={"Authorization": "Bearer token"},
    )
    assert response.status_code == 201

    session = SessionLocal()
    try:
        rows = await asyncio.to_thread(session.execute, select(Task))
        titles = {task.title for task in rows.scalars().all()}
    finally:
        await asyncio.to_thread(session.close)

    assert "Новое задание" in titles


@pytest.mark.anyio
async def test_assigned_tasks_require_auth(async_client):
    response = await async_client.get("/api/tasks/assigned")
    assert response.status_code in {401, 403}


@pytest.mark.anyio
async def test_assigned_tasks_only_for_current_user(async_client, seeded_users):
    student_user = seeded_users["student"]

    async def override_user():
        return student_user

    api_app.dependency_overrides[get_current_user] = override_user

    session = SessionLocal()
    try:
        await asyncio.to_thread(session.execute, delete(TaskAssignment))
        await asyncio.to_thread(session.execute, delete(Task))
        task_for_student = Task(
            title="Личное задание",
            description="Задание для конкретного студента",
            task_type="math",
            status=TaskStatus.ACTIVE,
        )
        task_for_other = Task(
            title="Чужое задание",
            description="Задание для другого пользователя",
            task_type="math",
            status=TaskStatus.ACTIVE,
        )
        session.add_all([task_for_student, task_for_other])
        await asyncio.to_thread(session.flush)
        session.add(TaskAssignment(task_id=task_for_student.id, user_id=student_user.id))
        await asyncio.to_thread(session.commit)
    finally:
        await asyncio.to_thread(session.close)

    response = await async_client.get(
        "/api/tasks/assigned",
        headers={"Authorization": "Bearer token"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["title"] == "Личное задание"