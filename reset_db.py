"""
Скрипт для полного сброса и пересоздания базы данных
ВНИМАНИЕ: Это удалит все данные!
Запуск: python reset_db.py
"""
from app.database import SessionLocal, sync_engine
from app.models import Base, User, Task, ShopItem, UserRole
from app.auth import AuthService
import json


def reset_database():
    """Сбросить и пересоздать базу данных"""

    print("⚠️  ВНИМАНИЕ: Это удалит все данные из базы!")
    print("🗑️  Удаляем все таблицы...")

    # Удаляем все таблицы
    Base.metadata.drop_all(bind=sync_engine)
    print("✅ Таблицы удалены")

    # Создаем таблицы заново
    print("📦 Создаем таблицы...")
    Base.metadata.create_all(bind=sync_engine)
    print("✅ Таблицы созданы")

    # Создаем тестовые данные
    create_sample_data()


def create_sample_data():
    """Создать тестовые данные"""

    db = SessionLocal()

    try:
        print("📦 Создаем тестовые данные...")

        # ===== ПОЛЬЗОВАТЕЛИ =====
        print("👥 Создаем пользователей...")

        users = [
            User(
                username="admin",
                email="admin@example.com",
                password_hash=AuthService.get_password_hash("admin123"),
                full_name="Администратор",
                role=UserRole.ADMIN,
                coins=10000,
                level=99,
                experience=99999,
                is_active=True,
                is_verified=True
            ),
            User(
                username="teacher",
                email="teacher@example.com",
                password_hash=AuthService.get_password_hash("teacher123"),
                full_name="Учитель Иванов",
                role=UserRole.TEACHER,
                coins=1000,
                level=10,
                experience=10000,
                is_active=True,
                is_verified=True
            ),
            User(
                username="student1",
                email="student1@example.com",
                password_hash=AuthService.get_password_hash("student123"),
                full_name="Петров Петр",
                role=UserRole.STUDENT,
                coins=250,
                level=3,
                experience=700,
                tasks_completed=15,
                average_score=78.5,
                is_active=True,
                is_verified=True
            ),
            User(
                username="student2",
                email="student2@example.com",
                password_hash=AuthService.get_password_hash("student123"),
                full_name="Сидорова Мария",
                role=UserRole.STUDENT,
                coins=180,
                level=2,
                experience=350,
                tasks_completed=8,
                average_score=85.0,
                is_active=True,
                is_verified=True
            ),
            User(
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
        ]

        for user in users:
            db.add(user)

        db.commit()
        print(f"✅ Создано {len(users)} пользователей")

        # ===== ЗАДАНИЯ =====
        print("📝 Создаем задания...")

        tasks = [
            Task(
                title="Решить квадратное уравнение",
                description="Решите уравнение: x² - 5x + 6 = 0\n\nПокажите полное решение с объяснением.",
                task_type="math",
                subject="Математика",
                difficulty=2,
                reward_coins=20,
                reward_exp=100,
                checking_criteria=json.dumps({
                    "keywords": ["x1", "x2", "дискриминант", "корни"],
                    "min_length": 50
                }, ensure_ascii=False),
                example_solution="D = b² - 4ac = 25 - 24 = 1\nx1 = (5+1)/2 = 3\nx2 = (5-1)/2 = 2",
                created_by=2  # teacher
            ),
            Task(
                title="Задача на движение",
                description="Два велосипедиста выехали навстречу друг другу из городов, расстояние между которыми 60 км. Скорость первого 12 км/ч, второго 18 км/ч. Через сколько времени они встретятся?",
                task_type="math",
                subject="Математика",
                difficulty=3,
                reward_coins=30,
                reward_exp=150,
                checking_criteria=json.dumps({
                    "keywords": ["скорость", "время", "расстояние", "встреча"],
                    "min_length": 80
                }, ensure_ascii=False),
                created_by=2
            ),
            Task(
                title="Сочинение: Моя любимая книга",
                description="Напишите сочинение о вашей любимой книге. Объем: не менее 150 слов.\n\nУкажите:\n- Название и автора\n- Краткий сюжет\n- Что вам понравилось\n- Чему научила книга",
                task_type="essay",
                subject="Литература",
                difficulty=2,
                reward_coins=25,
                reward_exp=120,
                checking_criteria=json.dumps({
                    "keywords": ["книга", "автор", "герой", "сюжет"],
                    "min_length": 150
                }, ensure_ascii=False),
                created_by=2
            ),
            Task(
                title="Закон Ома",
                description="Решите задачу:\n\nНапряжение в цепи 12 В, сопротивление 4 Ом. Найдите силу тока.\n\nПокажите формулу и расчеты.",
                task_type="physics",
                subject="Физика",
                difficulty=2,
                reward_coins=20,
                reward_exp=100,
                checking_criteria=json.dumps({
                    "keywords": ["Ом", "ток", "напряжение", "сопротивление", "I=U/R"],
                    "min_length": 40
                }, ensure_ascii=False),
                example_solution="I = U/R = 12/4 = 3 А",
                created_by=2
            ),
            Task(
                title="Таблица умножения на 7",
                description="Напишите таблицу умножения на 7 от 1 до 10.\n\nНапример: 7 × 1 = 7",
                task_type="math",
                subject="Математика",
                difficulty=1,
                reward_coins=10,
                reward_exp=50,
                checking_criteria=json.dumps({
                    "keywords": ["7", "×", "="],
                    "min_length": 100
                }, ensure_ascii=False),
                created_by=2
            ),
            Task(
                title="Химические элементы",
                description="Напишите химические символы и названия первых 10 элементов таблицы Менделеева.",
                task_type="chemistry",
                subject="Химия",
                difficulty=1,
                reward_coins=15,
                reward_exp=75,
                checking_criteria=json.dumps({
                    "keywords": ["H", "He", "Li", "водород", "гелий"],
                    "min_length": 50
                }, ensure_ascii=False),
                created_by=2
            )
        ]

        for task in tasks:
            db.add(task)

        db.commit()
        print(f"✅ Создано {len(tasks)} заданий")

        # ===== МАГАЗИН =====
        print("🛍️  Создаем товары в магазине...")

        shop_items = [
            # Аватары
            ShopItem(
                name="Золотая звезда",
                description="Эксклюзивная золотая звезда для вашего профиля",
                price_coins=100,
                item_type="avatar",
                item_data=json.dumps({"icon": "⭐"}),
                is_available=True
            ),
            ShopItem(
                name="Ракета",
                description="Аватар ракеты для амбициозных учеников",
                price_coins=150,
                item_type="avatar",
                item_data=json.dumps({"icon": "🚀"}),
                is_available=True
            ),
            ShopItem(
                name="Корона",
                description="Корона для лидеров рейтинга",
                price_coins=300,
                item_type="avatar",
                item_data=json.dumps({"icon": "👑"}),
                is_available=True
            ),

            # Бейджи
            ShopItem(
                name="Бейдж 'Отличник'",
                description="Значок за отличную учебу",
                price_coins=50,
                item_type="badge",
                item_data=json.dumps({"badge_id": "excellent_student"}),
                is_available=True
            ),
            ShopItem(
                name="Бейдж 'Математик'",
                description="За решение 100 математических задач",
                price_coins=200,
                item_type="badge",
                item_data=json.dumps({"badge_id": "math_master"}),
                is_available=True
            ),

            # Темы
            ShopItem(
                name="Темная тема",
                description="Классическая темная тема для интерфейса",
                price_coins=80,
                item_type="theme",
                item_data=json.dumps({"theme_id": "dark"}),
                is_available=True
            ),

            # Power-ups
            ShopItem(
                name="Двойные монеты",
                description="Получайте x2 монеты за следующие 5 заданий",
                price_coins=100,
                item_type="power_up",
                item_data=json.dumps({"type": "double_coins", "duration": 5}),
                is_available=True,
                stock=None
            ),
            ShopItem(
                name="Подсказка",
                description="Получить подсказку для любого задания",
                price_coins=50,
                item_type="hint",
                item_data=json.dumps({"type": "hint"}),
                is_available=True,
                stock=None
            )
        ]

        for item in shop_items:
            db.add(item)

        db.commit()
        print(f"✅ Создано {len(shop_items)} товаров")

        print("\n🎉 База данных успешно создана!")
        print("\n📋 Тестовые учетные данные:")
        print("   Админ:    admin / admin123")
        print("   Учитель:  teacher / teacher123")
        print("   Ученик 1: student1 / student123")
        print("   Ученик 2: student2 / student123")
        print("   Иван:     ivan / ivan123")
        print("\n🌐 Запустите сервер: python -m uvicorn app.main:app --reload")
        print("📚 API документация: http://localhost:8000/api/docs")
        print("🖥️  Веб-интерфейс: http://localhost:8000")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()

    finally:
        db.close()


if __name__ == "__main__":
    reset_database()