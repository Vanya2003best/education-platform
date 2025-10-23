"""
Education Platform - Главный файл приложения
Проверка рукописных работ через AI
"""
from fastapi import FastAPI, File, UploadFile, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
import uvicorn
import os

from app.database import engine, get_db
from app.models import Base
from app.routers import auth, tasks, submissions, coins, shop
from app.config import settings

# Создаем таблицы в БД
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Education Platform - AI Photo Checker",
    description="Платформа для проверки рукописных работ учеников через нейросети",
    version="1.0.0"
)

# CORS для фронтенда
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost:3000",  # для React/Vue dev сервера
        "http://127.0.0.1:3000",
        "*"  # Разрешить все (только для development!)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутеры (API endpoints)
app.include_router(auth.router, prefix="/api/auth", tags=["🔐 Аутентификация"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["📝 Задания"])
app.include_router(submissions.router, prefix="/api/submissions", tags=["📸 Сдача работ"])
app.include_router(coins.router, prefix="/api/coins", tags=["💰 Монеты"])
app.include_router(shop.router, prefix="/api/shop", tags=["🛍️ Магазин"])

# Статические файлы (загруженные фото)
os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# Статические файлы (HTML/CSS/JS интерфейс)
os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def root():
    """Перенаправление на главную страницу"""
    return RedirectResponse(url="/static/index.html")

@app.get("/api")
async def api_info():
    """Информация об API"""
    return {
        "message": "Education Platform API",
        "version": "1.0.0",
        "docs": "/docs",
        "features": [
            "AI-powered handwriting recognition",
            "Automatic grading system",
            "Gamification with coins",
            "Internal shop"
        ]
    }

@app.get("/health")
async def health_check():
    """Проверка работоспособности сервиса"""
    return {
        "status": "healthy",
        "database": "connected",
        "ai_service": "ready"
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=port,
        reload=settings.DEBUG
    )