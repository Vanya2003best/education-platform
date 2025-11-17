"""Reusable SQLAlchemy filters for task queries."""
from typing import Any
from sqlalchemy import or_

from app.models import Task, TaskStatus
def _status_variants(status: TaskStatus) -> tuple[Any, ...]:
    """Return a tuple with possible DB representations for ``status``.

    SQLite stores Enum values as plain strings, but depending on the SQLAlchemy
    version (and even the Python version), that string could be either the
    Enum's ``name`` (``"ACTIVE"``) or its ``value`` (``"active"``).  Some
    legacy rows may also store uppercase/lowercase variations of the raw value.
    To make filtering resilient across environments we generate a small set of
    acceptable values once and reuse it when building filters.
    """

    variants: set[Any] = {status}
    raw_value = getattr(status, "value", None)
    if isinstance(raw_value, str):
        variants.add(raw_value)
        variants.add(raw_value.lower())
        variants.add(raw_value.upper())
    raw_name = getattr(status, "name", None)
    if isinstance(raw_name, str):
        variants.add(raw_name)

    return tuple(variants)


_ACTIVE_STATUS_VALUES: tuple[Any, ...] = _status_variants(TaskStatus.ACTIVE)


def task_is_effectively_active():
    """Reusable SQLAlchemy filters for task queries."""

from sqlalchemy import String, cast, func, or_

from app.models import Task, TaskStatus


def task_is_effectively_active():
    """Return a filter that treats NULL statuses as active tasks.

    SQLite represents Enum columns as plain strings, but depending on the
    SQLAlchemy version those strings can surface as ``"active"``, ``"ACTIVE"``
    or even ``"TaskStatus.ACTIVE"``.  Comparing against the Enum constant alone
    therefore misses rows on some platforms (notably Windows/Python 3.10).  To
    keep the behaviour stable we compare both against the Enum value and the
    lower-cased textual representation of the column, ensuring every variant of
    "active" is treated as active.
    """

    status_as_text = func.lower(cast(Task.status, String))
    return or_(
        Task.status == TaskStatus.ACTIVE,
        status_as_text == TaskStatus.ACTIVE.value,
        Task.status.is_(None),
    )