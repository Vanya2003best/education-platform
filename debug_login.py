"""
Отладка проблемы с логином
Запуск: python debug_login.py
"""
import asyncio
from app.database import AsyncSessionLocal
from app.models import User
from app.auth import AuthService
from sqlalchemy import select


async def test_login():
    print("🔍 Тестирование процесса логина...\n")

    async with AsyncSessionLocal() as db:
        try:
            # 1. Проверяем наличие пользователя
            print("1️⃣ Ищем пользователя 'admin'...")
            result = await db.execute(
                select(User).where(User.username == 'admin')
            )
            user = result.scalar_one_or_none()

            if not user:
                print("   ❌ Пользователь не найден!")
                return

            print(f"   ✅ Пользователь найден: {user.username}")
            print(f"   Email: {user.email}")
            print(f"   Role: {user.role}")
            print(f"   Role type: {type(user.role)}")
            print(f"   Role value: {user.role.value if hasattr(user.role, 'value') else 'NO VALUE'}")

            # 2. Проверяем хеш пароля
            print("\n2️⃣ Проверяем хеш пароля...")
            print(f"   Хеш: {user.password_hash[:50]}...")

            try:
                is_valid = AuthService.verify_password("admin123", user.password_hash)
                print(f"   ✅ Проверка пароля: {'УСПЕШНО' if is_valid else 'НЕУДАЧНО'}")
            except Exception as e:
                print(f"   ❌ Ошибка проверки пароля: {e}")
                import traceback
                traceback.print_exc()
                return

            # 3. Проверяем создание токена
            print("\n3️⃣ Тестируем создание токенов...")
            try:
                tokens = AuthService.create_tokens(user.id, user.role.value)
                print(f"   ✅ Токены созданы!")
                print(f"   Access token: {tokens['access_token'][:50]}...")
            except Exception as e:
                print(f"   ❌ Ошибка создания токенов: {e}")
                import traceback
                traceback.print_exc()
                return

            print("\n✅ ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ!")
            print("\nПроблема не в логике, а скорее всего в:")
            print("   - Отсутствии импортов в app/auth.py")
            print("   - Неправильной конфигурации middleware")

        except Exception as e:
            print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_login())