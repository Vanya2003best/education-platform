"""
Проверка пользователей в базе данных
Запуск: python test_users.py
"""
from app.database import SessionLocal
from app.models import User
from app.auth import AuthService

db = SessionLocal()

try:
    users = db.query(User).all()

    print("=" * 60)
    print(f"👥 ПОЛЬЗОВАТЕЛИ В БАЗЕ ДАННЫХ: {len(users)}")
    print("=" * 60)

    if not users:
        print("\n❌ ПОЛЬЗОВАТЕЛИ НЕ НАЙДЕНЫ!")
        print("\n💡 Решение:")
        print("   python quick_fix.py")
        print("   или")
        print("   python minimal_setup.py")
    else:
        for user in users:
            print(f"\n📋 Пользователь: {user.username}")
            print(f"   Email: {user.email}")
            print(f"   Роль: {user.role.value}")
            print(f"   Активен: {user.is_active}")
            print(f"   Хеш пароля: {user.password_hash[:30]}...")

            # Пробуем стандартные пароли
            test_passwords = {
                "admin": "admin123",
                "teacher": "teacher123",
                "student1": "student123",
                "student2": "student123",
                "ivan": "ivan123"
            }

            if user.username in test_passwords:
                password = test_passwords[user.username]
                try:
                    is_valid = AuthService.verify_password(password, user.password_hash)
                    if is_valid:
                        print(f"   ✅ Пароль '{password}' - РАБОТАЕТ!")
                    else:
                        print(f"   ❌ Пароль '{password}' - НЕ РАБОТАЕТ!")
                        print(f"   💡 Запустите: python quick_fix.py")
                except Exception as e:
                    print(f"   ⚠️  Ошибка проверки пароля: {e}")

    print("\n" + "=" * 60)

except Exception as e:
    print(f"❌ ОШИБКА: {e}")
    import traceback

    traceback.print_exc()

finally:
    db.close()