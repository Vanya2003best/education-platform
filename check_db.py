"""
Скрипт для проверки состояния базы данных
Запуск: python check_db.py
"""
from app.database import SessionLocal, sync_engine
from app.models import User, Task, ShopItem
from app.auth import AuthService
from sqlalchemy import inspect


def check_database():
    """Проверить состояние базы данных"""

    print("🔍 Проверка базы данных Education Platform\n")
    print("=" * 60)

    # Проверка подключения
    try:
        connection = sync_engine.connect()
        print("✅ Подключение к базе данных: OK")
        connection.close()
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
        return

    # Проверка таблиц
    try:
        inspector = inspect(sync_engine)
        tables = inspector.get_table_names()
        print(f"✅ Найдено таблиц: {len(tables)}")
        print(f"   Таблицы: {', '.join(tables[:5])}...")
    except Exception as e:
        print(f"❌ Ошибка проверки таблиц: {e}")
        return

    print("\n" + "=" * 60)

    # Проверка данных
    db = SessionLocal()

    try:
        # Пользователи
        users = db.query(User).all()
        print(f"\n👥 ПОЛЬЗОВАТЕЛИ ({len(users)} шт.):")
        if users:
            for user in users:
                print(f"   • {user.username:<15} | {user.email:<25} | Роль: {user.role.value}")
        else:
            print("   ⚠️  Пользователи не найдены! Запустите: python reset_db.py")

        # Задания
        tasks = db.query(Task).all()
        print(f"\n📝 ЗАДАНИЯ ({len(tasks)} шт.):")
        if tasks:
            for task in tasks[:3]:
                print(f"   • {task.title[:50]:<50} | {task.subject}")
            if len(tasks) > 3:
                print(f"   ... и еще {len(tasks) - 3} заданий")
        else:
            print("   ⚠️  Задания не найдены!")

        # Товары
        items = db.query(ShopItem).all()
        print(f"\n🛍️  ТОВАРЫ В МАГАЗИНЕ ({len(items)} шт.):")
        if items:
            for item in items[:3]:
                print(f"   • {item.name:<30} | {item.price_coins} монет")
            if len(items) > 3:
                print(f"   ... и еще {len(items) - 3} товаров")
        else:
            print("   ⚠️  Товары не найдены!")

        # Проверка хешей паролей
        print(f"\n🔐 ПРОВЕРКА ПАРОЛЕЙ:")
        if users:
            test_user = users[0]
            print(f"   Проверяем пользователя: {test_user.username}")
            print(f"   Хеш пароля: {test_user.password_hash[:50]}...")

            # Пробуем проверить тестовый пароль
            if test_user.username == "student1":
                is_valid = AuthService.verify_password("student123", test_user.password_hash)
                if is_valid:
                    print("   ✅ Пароль 'student123' валиден!")
                else:
                    print("   ❌ Пароль 'student123' НЕ валиден! ОШИБКА!")
            elif test_user.username == "admin":
                is_valid = AuthService.verify_password("admin123", test_user.password_hash)
                if is_valid:
                    print("   ✅ Пароль 'admin123' валиден!")
                else:
                    print("   ❌ Пароль 'admin123' НЕ валиден! ОШИБКА!")

        print("\n" + "=" * 60)
        print("\n✅ ДИАГНОСТИКА ЗАВЕРШЕНА\n")

        # Рекомендации
        if not users or len(users) == 0:
            print("⚠️  РЕКОМЕНДАЦИЯ: Запустите python reset_db.py для создания тестовых данных\n")
        else:
            print("✅ База данных выглядит нормально!\n")
            print("📋 Тестовые учетные данные для входа:")
            if any(u.username == "admin" for u in users):
                print("   • admin / admin123")
            if any(u.username == "teacher" for u in users):
                print("   • teacher / teacher123")
            if any(u.username == "student1" for u in users):
                print("   • student1 / student123")
            print()

    except Exception as e:
        print(f"\n❌ Ошибка при проверке данных: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()


if __name__ == "__main__":
    check_database()