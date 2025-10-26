"""
Быстрое исправление проблемы с логином
Запуск: python quick_fix.py
"""
import sys
from app.database import SessionLocal, sync_engine
from app.models import Base, User, UserRole
from app.auth import AuthService


def quick_fix():
    """Быстро исправить проблему с логином"""

    print("🔧 Education Platform - Быстрое исправление")
    print("=" * 60)

    db = SessionLocal()

    try:
        # Проверяем существующих пользователей
        print("\n📋 Проверка пользователей...")
        users = db.query(User).all()

        if not users:
            print("❌ Пользователи не найдены!")
            print("   Создаем тестового пользователя...")

            # Создаем таблицы если их нет
            Base.metadata.create_all(bind=sync_engine)

            # Создаем тестового пользователя
            test_user = User(
                username="ivan",
                email="ivan@example.com",
                password_hash=AuthService.get_password_hash("ivan123"),
                full_name="Иван Иванов",
                role=UserRole.STUDENT,
                coins=100,
                level=1,
                experience=0,
                is_active=True,
                is_verified=True
            )

            db.add(test_user)
            db.commit()

            print("✅ Создан пользователь: ivan / ivan123")
        else:
            print(f"✅ Найдено пользователей: {len(users)}")

            # Проверяем пароли
            print("\n🔐 Проверка паролей...")

            fixed_count = 0
            for user in users:
                # Пытаемся определить правильный пароль
                test_passwords = {
                    "admin": "admin123",
                    "teacher": "teacher123",
                    "student1": "student123",
                    "student2": "student123",
                    "ivan": "ivan123"
                }

                expected_password = test_passwords.get(user.username, "password123")

                # Проверяем, работает ли пароль
                try:
                    is_valid = AuthService.verify_password(expected_password, user.password_hash)

                    if is_valid:
                        print(f"   ✅ {user.username} - пароль OK")
                    else:
                        print(f"   ❌ {user.username} - пароль НЕВЕРНЫЙ, исправляем...")

                        # Исправляем хеш пароля
                        user.password_hash = AuthService.get_password_hash(expected_password)
                        fixed_count += 1

                        print(f"   ✅ {user.username} - пароль исправлен на '{expected_password}'")

                except Exception as e:
                    print(f"   ⚠️  {user.username} - ошибка проверки: {e}")
                    # На всякий случай обновляем хеш
                    user.password_hash = AuthService.get_password_hash(expected_password)
                    fixed_count += 1
                    print(f"   ✅ {user.username} - пароль пересоздан")

            if fixed_count > 0:
                db.commit()
                print(f"\n✅ Исправлено паролей: {fixed_count}")
            else:
                print("\n✅ Все пароли корректны!")

        print("\n" + "=" * 60)
        print("✅ ИСПРАВЛЕНИЕ ЗАВЕРШЕНО!\n")

        print("📋 Доступные учетные данные:")
        users = db.query(User).all()
        for user in users:
            test_passwords = {
                "admin": "admin123",
                "teacher": "teacher123",
                "student1": "student123",
                "student2": "student123",
                "ivan": "ivan123"
            }
            password = test_passwords.get(user.username, "password123")
            print(f"   • {user.username:15} / {password}")

        print("\n🚀 Теперь запустите сервер:")
        print("   python -m uvicorn app.main:app --reload")
        print("\n🌐 И откройте: http://127.0.0.1:8000\n")

        return True

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        db.close()


if __name__ == "__main__":
    success = quick_fix()
    sys.exit(0 if success else 1)