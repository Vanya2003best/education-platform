"""
Скрипт для заполнения базы данных тестовыми данными
Запуск: python seed.py
"""
from app.database import SessionLocal, sync_engine
from app.models import Base, User, Task, ShopItem
from app.auth import AuthService
import json


def create_sample_data():
    """Создать тестовые данные"""

    # Создаем таблицы
    Base.metadata.create_all(bind=sync_engine)

    db = SessionLocal()

    try:
        # Проверяем, есть ли уже данные
        if db.query(User).first():
            print("⚠️  База данных уже содержит данные. Пропускаем...")
            return

        print("📦 Создаем тестовые данные...")

        # ===== ПОЛЬЗОВАТЕЛИ =====
        print("👥 Создаем пользователей...")

        users = [
            User(
                username="teacher",
                email="teacher@example.com",
                password_hash=AuthService("teacher123"),
                full_name="Учитель Иванов",
                coins=1000,
                level=10,
                experience=10000
            ),
            User(
                username="student1",
                email="student1@example.com",
                password_hash=AuthService("student123"),
                full_name="Петров Петр",
                coins=250,
                level=3,
                experience=700,
                tasks_completed=15,
                average_score=78.5
            ),
            User(
                username="student2",
                email="student2@example.com",
                password_hash=AuthService("student123"),
                full_name="Сидорова Мария",
                coins=180,
                level=2,
                experience=350,
                tasks_completed=8,
                average_score=85.0
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
                created_by=1
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
                created_by=1
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
                created_by=1
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
                created_by=1
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
                created_by=1
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
                created_by=1
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
                price=100,
                item_type="avatar",
                item_data=json.dumps({"icon": "⭐"}),
                available=True
            ),
            ShopItem(
                name="Ракета",
                description="Аватар ракеты для амбициозных учеников",
                price=150,
                item_type="avatar",
                item_data=json.dumps({"icon": "🚀"}),
                available=True
            ),
            ShopItem(
                name="Корона",
                description="Корона для лидеров рейтинга",
                price=300,
                item_type="avatar",
                item_data=json.dumps({"icon": "👑"}),
                available=True
            ),

            # Бейджи
            ShopItem(
                name="Бейдж 'Отличник'",
                description="Значок за отличную учебу",
                price=50,
                item_type="badge",
                item_data=json.dumps({"badge_id": "excellent_student"}),
                available=True
            ),
            ShopItem(
                name="Бейдж 'Математик'",
                description="За решение 100 математических задач",
                price=200,
                item_type="badge",
                item_data=json.dumps({"badge_id": "math_master"}),
                available=True
            ),
            ShopItem(
                name="Бейдж 'Писатель'",
                description="За написание 50 сочинений",
                price=200,
                item_type="badge",
                item_data=json.dumps({"badge_id": "writer"}),
                available=True
            ),

            # Темы оформления
            ShopItem(
                name="Темная тема",
                description="Классическая темная тема для интерфейса",
                price=80,
                item_type="theme",
                item_data=json.dumps({"theme_id": "dark"}),
                available=True
            ),
            ShopItem(
                name="Космическая тема",
                description="Красивая тема с космосом",
                price=120,
                item_type="theme",
                item_data=json.dumps({"theme_id": "space"}),
                available=True
            ),

            # Power-ups
            ShopItem(
                name="Двойные монеты",
                description="Получайте x2 монеты за следующие 5 заданий",
                price=100,
                item_type="power_up",
                item_data=json.dumps({"type": "double_coins", "duration": 5}),
                available=True,
                stock=None  # Бесконечный запас
            ),
            ShopItem(
                name="Подсказка",
                description="Получить подсказку для любого задания",
                price=50,
                item_type="hint",
                item_data=json.dumps({"type": "hint"}),
                available=True,
                stock=None
            )
        ]

        for item in shop_items:
            db.add(item)

        db.commit()
        print(f"✅ Создано {len(shop_items)} товаров")

        print("\n🎉 Тестовые данные успешно созданы!")
        print("\n📋 Тестовые учетные данные:")
        print("   Учитель: teacher / teacher123")
        print("   Ученик 1: student1 / student123")
        print("   Ученик 2: student2 / student123")
        print("\n🌐 Запустите сервер: uvicorn app.main:app --reload")
        print("📚 API документация: http://localhost:8000/docs")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        db.rollback()

    finally:
        db.close()


if __name__ == "__main__":
    create_sample_data()