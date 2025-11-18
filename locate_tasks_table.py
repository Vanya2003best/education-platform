#!/usr/bin/env python3
"""Utility script to inspect where the ``tasks`` table actually lives.

The admin panel sometimes reports 404s when it cannot locate a task to
update or delete. Most of the time this is caused by pointing the API at an
unexpected database file or schema. This helper prints the effective
SQLAlchemy URL, the resolved filesystem path (for SQLite), and whether the
``tasks`` table is present.

Example::

    python locate_tasks_table.py --details
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, select, func
from sqlalchemy.engine.url import make_url

from app.config import settings
from app.database import sync_engine
from app.models import Task


def _describe_database_url(raw_url: str) -> dict[str, Any]:
    """Return a structured representation of the configured DB URL."""

    url = make_url(raw_url)
    info: dict[str, Any] = {
        "drivername": url.drivername,
        "database": url.database,
        "username": url.username,
        "host": url.host,
        "port": url.port,
    }

    if url.drivername.startswith("sqlite") and url.database:
        # Normalise relative SQLite paths so we can tell where the file lives.
        db_path = Path(url.database).expanduser().resolve()
        info["database_path"] = str(db_path)
        info["database_exists"] = db_path.exists()

    return info


def locate_task_table(sample: int = 5) -> dict[str, Any]:
    """Inspect the metadata and return useful diagnostics about ``tasks``."""

    metadata = Task.__table__
    inspector = inspect(sync_engine)
    schema = metadata.schema
    table_name = metadata.name
    has_table = inspector.has_table(table_name, schema=schema)

    payload: dict[str, Any] = {
        "table": table_name if not schema else f"{schema}.{table_name}",
        "schema": schema,
        "exists": has_table,
    }

    if not has_table:
        return payload

    with sync_engine.connect() as conn:
        # берём несколько id для примера
        result = conn.execute(select(Task.id).order_by(Task.id).limit(sample))
        payload["sample_task_ids"] = [row[0] for row in result]

        # считаем строки через COUNT(*), а не через get_table_options
        row_count = conn.execute(
            select(func.count()).select_from(Task)
        ).scalar_one()
        payload["row_count"] = row_count

    return payload

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--details",
        action="store_true",
        help="Print the gathered information as pretty JSON.",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=5,
        help="How many task ids to sample when the table exists (default: 5).",
    )
    args = parser.parse_args()

    db_info = _describe_database_url(settings.DATABASE_URL)
    task_info = locate_task_table(sample=max(1, args.sample))

    if args.details:
        print(
            json.dumps(
                {"database": db_info, "task_table": task_info},
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(f"Database URL → {db_info}")
        print(f"Task table → {task_info}")


if __name__ == "__main__":
    main()