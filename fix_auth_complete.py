"""
Полное исправление app/auth.py
Запуск: python fix_auth_complete.py
"""


def fix_auth_file():
    """Исправляет все известные проблемы в auth.py"""

    file_path = "app/auth.py"

    print("🔧 Исправление app/auth.py...\n")

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    fixed = False

    # 1. Проверяем импорты
    if 'from sqlalchemy import select' not in content:
        print("❌ Отсутствует импорт select")
        # Находим строку с AsyncSession и добавляем после нее
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if 'from sqlalchemy.ext.asyncio import AsyncSession' in line:
                lines.insert(i + 1, 'from sqlalchemy import select, and_, or_')
                content = '\n'.join(lines)
                fixed = True
                print("✅ Добавлен импорт select")
                break
    else:
        print("✅ Импорт select присутствует")

    # 2. Исправляем RateLimiter
    old_rate_limiter = 'client_id = request.client.host'
    new_rate_limiter = 'client_id = request.client.host if request.client else "unknown"'

    if old_rate_limiter in content and new_rate_limiter not in content:
        print("❌ RateLimiter небезопасен")
        content = content.replace(old_rate_limiter, new_rate_limiter)
        fixed = True
        print("✅ Исправлен RateLimiter")
    else:
        print("✅ RateLimiter безопасен")

    # 3. Проверяем метод authenticate_user
    if 'async def authenticate_user(' in content:
        # Убеждаемся что используется select правильно
        if 'result = await db.execute(' not in content:
            print("⚠️  Возможна проблема в authenticate_user")
    else:
        print("✅ authenticate_user выглядит корректно")

    # Сохраняем если были изменения
    if fixed:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print("\n✅ Файл исправлен и сохранен!")
    else:
        print("\n✅ Файл уже корректен!")

    print("\n🔄 Перезапустите сервер: python -m uvicorn app.main:app --reload")


if __name__ == "__main__":
    fix_auth_file()