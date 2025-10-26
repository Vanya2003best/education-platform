"""
API для внутреннего магазина
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.database import get_async_db
from app.models import ShopItem, Purchase, User, Transaction
from app.schemas import ShopItemResponse, PurchaseCreate, PurchaseResponse
from app.auth import get_current_user

router = APIRouter()


@router.get("/items", response_model=List[ShopItemResponse])
async def get_shop_items(
        item_type: str = None,
        db: AsyncSession = Depends(get_async_db)
):
    """
    Получить товары в магазине
    """
    query = select(ShopItem).where(ShopItem.is_available == True)

    if item_type:
        query = query.where(ShopItem.item_type == item_type)

    result = await db.execute(query.order_by(ShopItem.price_coins))
    items = result.scalars().all()

    return items


@router.get("/items/{item_id}", response_model=ShopItemResponse)
async def get_shop_item(
        item_id: int,
        db: AsyncSession = Depends(get_async_db)
):
    """
    Получить конкретный товар
    """
    result = await db.execute(
        select(ShopItem).where(
            ShopItem.id == item_id,
            ShopItem.is_available == True
        )
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Товар не найден")

    return item


@router.post("/purchase", response_model=PurchaseResponse)
async def purchase_item(
        purchase_data: PurchaseCreate,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db)
):
    """
    Купить товар в магазине
    """
    # Получаем товар
    result = await db.execute(
        select(ShopItem).where(
            ShopItem.id == purchase_data.item_id,
            ShopItem.is_available == True
        )
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Товар не найден или недоступен")

    # Проверяем наличие товара
    if item.stock is not None and item.stock <= 0:
        raise HTTPException(status_code=400, detail="Товар закончился")

    # Проверяем баланс
    if current_user.coins < item.price_coins:
        raise HTTPException(
            status_code=400,
            detail=f"Недостаточно монет. Нужно: {item.price_coins}, есть: {current_user.coins}"
        )

    # Проверяем, не куплен ли уже товар (для уникальных товаров)
    if item.item_type in ['avatar', 'badge']:
        existing = await db.execute(
            select(Purchase).where(
                Purchase.user_id == current_user.id,
                Purchase.item_id == item.id
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Вы уже купили этот товар")

    # Создаем покупку
    purchase = Purchase(
        user_id=current_user.id,
        item_id=item.id,
        price_coins=item.price_coins,
        price_gems=item.price_gems or 0,
        discount_applied=item.discount_percentage or 0
    )
    db.add(purchase)

    # Списываем монеты
    current_user.coins -= item.price_coins

    # Уменьшаем stock
    if item.stock is not None:
        item.stock -= 1
        if item.stock == 0:
            item.is_available = False

    # Увеличиваем счетчик покупок
    item.purchases_count += 1

    # Создаем транзакцию
    transaction = Transaction(
        user_id=current_user.id,
        coins_amount=-item.price_coins,
        transaction_type="purchase",
        category="shop",
        description=f"Покупка: {item.name}",
        related_purchase_id=purchase.id,
        coins_balance=current_user.coins
    )
    db.add(transaction)

    await db.commit()
    await db.refresh(purchase)

    return purchase


@router.get("/my-purchases")
async def get_my_purchases(
        skip: int = 0,
        limit: int = 50,
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_async_db)
):
    """
    Получить свои покупки
    """
    result = await db.execute(
        select(Purchase)
        .where(Purchase.user_id == current_user.id)
        .order_by(Purchase.purchased_at.desc())
        .offset(skip)
        .limit(limit)
    )
    purchases = result.scalars().all()

    response = []
    for p in purchases:
        # Получаем информацию о товаре
        item_result = await db.execute(
            select(ShopItem).where(ShopItem.id == p.item_id)
        )
        item = item_result.scalar_one_or_none()

        response.append({
            "id": p.id,
            "item_name": item.name if item else "Unknown",
            "item_type": item.item_type if item else "unknown",
            "price_paid": p.price_coins,
            "purchased_at": p.purchased_at
        })

    return response


@router.get("/categories")
async def get_shop_categories(db: AsyncSession = Depends(get_async_db)):
    """
    Получить доступные категории товаров
    """
    result = await db.execute(
        select(ShopItem.item_type)
        .where(ShopItem.is_available == True)
        .distinct()
    )
    categories = [row[0] for row in result.all()]

    return categories