"""
Добавляет колонку content_html в public.tasks (idempotent).
Запуск:  python migrations/add_content_html_column.py
Альтернатива: python -m migrations.add_content_html_column
"""
import os, sys, inspect
from sqlalchemy import text

# --- Подключаем корень проекта в sys.path ---
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    current_dir = os.path.dirname(os.path.abspath(inspect.getfile(inspect.currentframe())))

project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Теперь импорт доступен
from app.database import sync_engine

SQL = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'tasks'
          AND column_name  = 'content_html'
    ) THEN
        ALTER TABLE public.tasks ADD COLUMN content_html TEXT;
    END IF;
END
$$;
"""

def main():
    with sync_engine.begin() as conn:
        conn.execute(text(SQL))
    print("✅ Column public.tasks.content_html ensured (created if missing).")

if __name__ == "__main__":
    main()
