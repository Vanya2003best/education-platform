"""
Добавляет колонку content_html в таблицу public.tasks.
Запуск: python add_content_html_column.py
"""

from sqlalchemy import text, inspect
from app.database import sync_engine


def add_content_html_column():
    insp = inspect(sync_engine)

    # Проверим наличие таблицы и колонки (идемпотентность)
    has_tasks = insp.has_table("tasks", schema="public")
    if not has_tasks:
        raise RuntimeError("Таблица public.tasks не найдена. Убедитесь, что БД инициализирована.")

    columns = {col["name"] for col in insp.get_columns("tasks", schema="public")}
    if "content_html" in columns:
        print("✅ Колонка content_html уже существует — ничего делать не нужно.")
        return

    # Добавляем колонку
    ddl = "ALTER TABLE public.tasks ADD COLUMN content_html TEXT"
    with sync_engine.begin() as conn:
        conn.execute(text(ddl))

    print("✅ Колонка content_html успешно добавлена в public.tasks.")


if __name__ == "__main__":
    try:
        add_content_html_column()
    finally:
        # корректно закрываем коннектор
        sync_engine.dispose()
