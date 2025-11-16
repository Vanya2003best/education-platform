"""Reusable SQLAlchemy filters for task queries."""
from sqlalchemy import or_

from app.models import Task, TaskStatus


def task_is_effectively_active():
    """Return a filter that treats NULL statuses as active tasks."""
    return or_(Task.status == TaskStatus.ACTIVE, Task.status.is_(None))