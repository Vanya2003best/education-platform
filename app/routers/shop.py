"""
API для внутреннего магазина
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models import ShopItem, Purchase, User, Transaction
from app.schemas import ShopItemResponse, PurchaseCreate, PurchaseResponse
from app.auth import get_current_user

router = APIRouter()


@router.get("/items", response_model=List[ShopItemResponse])
async def get_shop_items(
        item_type: str = None,
        db: Session = Depends(get_db)
):
    """
    Получить товары в магазине
    """
    query = db.query(ShopItem).filter(ShopItem.available == True)

    if item_type:
        query = query.filter(ShopItem.item_type == item_type)

    items = query.order_by(ShopItem.price).all()

    return items


@router.get("/items/{item_id}", response_model=ShopItemResponse)
async def get_shop_item(item_id: int, db: Session = Depends(get_db)):
    """
    Получить конкретный товар
    """
    item = db.query(ShopItem).filter(
        ShopItem.id == item_id,
        ShopItem.available == True
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Товар не найден")

    return item


@router.post("/purchase", response_model=PurchaseResponse)
async def purchase_item(
        purchase_data: PurchaseCreate,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Купить товар в магазине
    """
    # Получаем товар
    item = db.query(ShopItem).filter(
        ShopItem.id == purchase_data.item_id,
        ShopItem.available == True
    ).first()

    if not item:
        raise HTTPException(status_code=404, detail="Товар не найден или недоступен")

    # Проверяем наличие товара
    if item.stock is not None and item.stock <= 0:
        raise HTTPException(status_code=400, detail="Товар закончился")

    # Проверяем баланс
    if current_user.coins < item.price:
        raise HTTPException(
            status_code=400,
            detail=f"Недостаточно монет. Нужно: {item.price}, есть: {current_user.coins}"
        )

    # Проверяем, не куплен ли уже товар (для уникальных товаров)
    if item.item_type in ['avatar', 'badge']:
        existing_purchase = db.query(Purchase).filter(
            Purchase.user_id == current_user.id,
            Purchase.item_id == item.id
        ).first()

        if existing_purchase:
            raise HTTPException(status_code=400, detail="Вы уже купили этот товар")

    # Создаем покупку
    purchase = Purchase(
        user_id=current_user.id,
        item_id=item.id,
        price_paid=item.price
    )
    db.add(purchase)

    # Списываем монеты
    current_user.coins -= item.price

    # Уменьшаем stock
    if item.stock is not None:
        item.stock -= 1
        if item.stock == 0:
            item.available = False

    # Создаем транзакцию
    transaction = Transaction(
        user_id=current_user.id,
        amount=-item.price,
        transaction_type="purchase",
        description=f"Покупка: {item.name}",
        related_purchase_id=purchase.id
    )
    db.add(transaction)

    db.commit()
    db.refresh(purchase)

    return purchase


@router.get("/my-purchases")
async def get_my_purchases(
        skip: int = 0,
        limit: int = 50,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db)
):
    """
    Получить свои покупки
    """
    purchases = db.query(Purchase).filter(
        Purchase.user_id == current_user.id
    ).order_by(
        Purchase.purchased_at.desc()
    ).offset(skip).limit(limit).all()

    result = []
    for p in purchases:
        item = db.query(ShopItem).filter(ShopItem.id == p.item_id).first()
        result.append({
            "id": p.id,
            "item_name": item.name if item else "Unknown",
            "item_type": item.item_type if item else "unknown",
            "price_paid": p.price_paid,
            "purchased_at": p.purchased_at
        })

    return result


@router.get("/categories")
async def get_shop_categories(db: Session = Depends(get_db)):
    """
    Получить доступные категории товаров
    """
    categories = db.query(ShopItem.item_type).filter(
        ShopItem.available == True
    ).distinct().all()

    return [c[0] for c in categories]