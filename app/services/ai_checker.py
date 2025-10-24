"""
Улучшенный AI сервис для проверки рукописных работ
с retry логикой, кэшированием и обработкой ошибок
"""
import base64
import json
import time
import asyncio
from typing import Dict, Any, Optional, List
from io import BytesIO
from PIL import Image
import cv2
import numpy as np
import pytesseract
from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential
import hashlib
import logging
from dataclasses import dataclass
from enum import Enum

from app.config import settings
from app.utils.cache import cache_manager, cache_result

logger = logging.getLogger(__name__)


class CheckingQuality(Enum):
    """Уровни качества проверки"""
    BASIC = "basic"      # Только OCR
    STANDARD = "standard"  # OCR + базовый AI
    ADVANCED = "advanced"  # OCR + GPT-4 Vision
    PREMIUM = "premium"   # Полный анализ с плагиат-чеком


@dataclass
class CheckingResult:
    """Результат проверки"""
    recognized_text: str
    score: float
    feedback: str
    detailed_analysis: Dict[str, Any]
    confidence_score: float
    processing_time: float
    status: str
    quality_level: CheckingQuality
    suggestions: List[str]
    plagiarism_score: Optional[float] = None


class ImagePreprocessor:
    """Предобработка изображений для улучшения OCR"""

    @staticmethod
    def preprocess(image_path: str) -> np.ndarray:
        """Комплексная предобработка изображения"""
        # Читаем изображение
        img = cv2.imread(image_path)

        # Конвертируем в grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Убираем шум
        denoised = cv2.fastNlMeansDenoising(gray, None, 10, 7, 21)

        # Адаптивная бинаризация
        binary = cv2.adaptiveThreshold(
            denoised, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )

        # Морфологические операции для улучшения текста
        kernel = np.ones((1, 1), np.uint8)
        morph = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

        # Выравнивание перспективы (если нужно)
        aligned = ImagePreprocessor._deskew(morph)

        return aligned

    @staticmethod
    def _deskew(image: np.ndarray) -> np.ndarray:
        """Выравнивание наклоненного текста"""
        coords = np.column_stack(np.where(image > 0))
        angle = cv2.minAreaRect(coords)[-1]

        if angle < -45:
            angle = -(90 + angle)
        else:
            angle = -angle

        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(
            image, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE
        )

        return rotated

    @staticmethod
    def enhance_contrast(image_path: str) -> Image.Image:
        """Улучшение контраста для PIL"""
        from PIL import ImageEnhance, ImageOps

        image = Image.open(image_path)

        # Конвертируем в grayscale
        image = image.convert('L')

        # Автоматическая коррекция уровней
        image = ImageOps.autocontrast(image)

        # Увеличиваем контраст
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(2.0)

        # Увеличиваем резкость
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(1.5)

        return image


class AIPhotoChecker:
    """Улучшенный сервис проверки с retry и кэшированием"""

    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None
        self.preprocessor = ImagePreprocessor()

    async def check_photo_submission(
        self,
        photo_path: str,
        task_description: str,
        task_type: str,
        checking_criteria: str,
        user_id: int,
        quality: CheckingQuality = CheckingQuality.STANDARD
    ) -> CheckingResult:
        """
        Главный метод проверки с выбором уровня качества
        """
        start_time = time.time()

        # Генерируем хеш для кэширования
        cache_key = self._generate_cache_key(photo_path, task_description)

        # Проверяем кэш
        cached_result = await cache_manager.get(f"check:{cache_key}")
        if cached_result and not settings.DEBUG:
            logger.info(f"Using cached result for {cache_key}")
            return CheckingResult(**cached_result)

        try:
            # Предобработка изображения
            processed_image = self.preprocessor.preprocess(photo_path)

            # OCR с несколькими попытками
            recognized_text = await self._perform_ocr(photo_path, processed_image)

            # Выбираем метод проверки в зависимости от quality
            if quality == CheckingQuality.BASIC:
                result = await self._basic_analysis(recognized_text, task_description)
            elif quality == CheckingQuality.ADVANCED or quality == CheckingQuality.PREMIUM:
                result = await self._advanced_analysis(
                    photo_path, recognized_text, task_description,
                    task_type, checking_criteria
                )

                # Для PREMIUM добавляем проверку на плагиат
                if quality == CheckingQuality.PREMIUM:
                    plagiarism_score = await self._check_plagiarism(recognized_text, user_id)
                    result["plagiarism_score"] = plagiarism_score
            else:  # STANDARD
                result = await self._standard_analysis(
                    recognized_text, task_description, task_type
                )

            processing_time = time.time() - start_time

            # Формируем результат
            checking_result = CheckingResult(
                recognized_text=recognized_text,
                score=result["score"],
                feedback=result["feedback"],
                detailed_analysis=result["detailed_analysis"],
                confidence_score=result.get("confidence", 0.8),
                processing_time=processing_time,
                status="checked",
                quality_level=quality,
                suggestions=result.get("suggestions", []),
                plagiarism_score=result.get("plagiarism_score")
            )

            # Кэшируем результат
            await cache_manager.set(
                f"check:{cache_key}",
                checking_result.__dict__,
                ttl=3600  # 1 час
            )

            return checking_result

        except Exception as e:
            logger.error(f"Error checking submission: {e}")
            return CheckingResult(
                recognized_text="",
                score=0,
                feedback=f"Ошибка при проверке: {str(e)}",
                detailed_analysis={"error": str(e)},
                confidence_score=0,
                processing_time=time.time() - start_time,
                status="failed",
                quality_level=quality,
                suggestions=["Попробуйте загрузить более четкое фото"]
            )

    async def _perform_ocr(self, photo_path: str, processed_image: np.ndarray) -> str:
        """OCR с несколькими методами"""
        texts = []

        # Метод 1: Обработанное изображение
        try:
            text1 = pytesseract.image_to_string(
                processed_image,
                lang=settings.OCR_LANGUAGE,
                config='--psm 6'  # Uniform block of text
            )
            texts.append(text1)
        except Exception as e:
            logger.warning(f"OCR method 1 failed: {e}")

        # Метод 2: Оригинальное изображение с улучшением контраста
        try:
            enhanced = self.preprocessor.enhance_contrast(photo_path)
            text2 = pytesseract.image_to_string(
                enhanced,
                lang=settings.OCR_LANGUAGE,
                config='--psm 3'  # Fully automatic
            )
            texts.append(text2)
        except Exception as e:
            logger.warning(f"OCR method 2 failed: {e}")

        # Выбираем лучший результат
        best_text = max(texts, key=len) if texts else ""

        # Очистка текста
        best_text = self._clean_ocr_text(best_text)

        return best_text

    def _clean_ocr_text(self, text: str) -> str:
        """Очистка распознанного текста"""
        # Убираем лишние символы
        import re

        # Убираем множественные пробелы
        text = re.sub(r'\s+', ' ', text)

        # Убираем специальные символы в начале строк
        text = re.sub(r'^[^\w\s]+', '', text, flags=re.MULTILINE)

        # Исправляем частые ошибки OCR
        replacements = {
            '|': 'I',
            '0': 'O',  # если в контексте букв
            '1': 'l',  # если в контексте букв
        }

        return text.strip()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    async def _advanced_analysis(
        self,
        photo_path: str,
        recognized_text: str,
        task_description: str,
        task_type: str,
        checking_criteria: str
    ) -> Dict[str, Any]:
        """Продвинутый анализ с GPT-4 Vision и retry"""

        # Кодируем изображение
        with open(photo_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        # Создаем промпт
        prompt = self._create_advanced_prompt(
            task_description, task_type, checking_criteria, recognized_text
        )

        # Запрос к GPT-4 Vision
        response = await self.client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": "Ты опытный преподаватель, проверяющий работы учеников. Будь объективным, но доброжелательным."
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            max_tokens=2000,
            temperature=settings.AI_TEMPERATURE,
            response_format={"type": "json_object"}
        )

        # Парсим результат
        result = json.loads(response.choices[0].message.content)

        return self._validate_ai_response(result)

    async def _standard_analysis(
        self,
        recognized_text: str,
        task_description: str,
        task_type: str
    ) -> Dict[str, Any]:
        """Стандартный анализ с базовым AI"""

        if not self.client:
            return await self._basic_analysis(recognized_text, task_description)

        try:
            # Запрос к GPT без изображения
            response = await self.client.chat.completions.create(
                model="gpt-4o-mini",  # Более дешевая модель
                messages=[
                    {
                        "role": "system",
                        "content": "Проверь работу ученика и дай оценку от 0 до 100."
                    },
                    {
                        "role": "user",
                        "content": f"""
                        Задание: {task_description}
                        Тип: {task_type}
                        
                        Ответ ученика:
                        {recognized_text}
                        
                        Оцени работу и верни JSON:
                        {{
                            "score": число 0-100,
                            "feedback": "краткий отзыв",
                            "detailed_analysis": {{
                                "правильные_моменты": [],
                                "ошибки": [],
                                "рекомендации": []
                            }},
                            "confidence": число 0-1,
                            "suggestions": []
                        }}
                        """
                    }
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )

            result = json.loads(response.choices[0].message.content)
            return self._validate_ai_response(result)

        except Exception as e:
            logger.error(f"Standard analysis error: {e}")
            return await self._basic_analysis(recognized_text, task_description)

    async def _basic_analysis(
        self,
        recognized_text: str,
        task_description: str
    ) -> Dict[str, Any]:
        """Базовый анализ без AI"""

        score = 0
        feedback_parts = []
        suggestions = []

        # Анализ длины
        text_length = len(recognized_text)
        if text_length > 50:
            score += 30
            feedback_parts.append("✅ Достаточный объем работы")
        else:
            feedback_parts.append("❌ Работа слишком короткая")
            suggestions.append("Напишите более развернутый ответ")

        # Проверка ключевых слов
        task_words = set(task_description.lower().split())
        text_words = set(recognized_text.lower().split())
        common_words = task_words & text_words

        relevance_score = len(common_words) / max(len(task_words), 1)
        score += int(relevance_score * 40)

        if relevance_score > 0.3:
            feedback_parts.append(f"✅ Работа соответствует заданию")
        else:
            feedback_parts.append("⚠️ Работа слабо связана с заданием")
            suggestions.append("Внимательно прочитайте задание")

        # Бонус за попытку
        score += 20

        return {
            "score": min(score, 100),
            "feedback": "\n".join(feedback_parts),
            "detailed_analysis": {
                "текст_распознан": text_length > 0,
                "длина_текста": text_length,
                "соответствие_заданию": f"{relevance_score:.0%}"
            },
            "confidence": 0.5,
            "suggestions": suggestions
        }

    async def _check_plagiarism(self, text: str, user_id: int) -> float:
        """Проверка на плагиат (сравнение с предыдущими работами)"""

        # Получаем хеш текста
        text_hash = hashlib.md5(text.encode()).hexdigest()

        # Проверяем в кэше похожие работы
        similar_works = await cache_manager.lrange(f"works:{user_id}", 0, 100)

        max_similarity = 0.0
        for work in similar_works:
            similarity = self._calculate_similarity(text, work)
            max_similarity = max(max_similarity, similarity)

        # Сохраняем текущую работу
        await cache_manager.lpush(f"works:{user_id}", text)

        # Возвращаем процент уникальности
        return 100 - (max_similarity * 100)

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Расчет схожести текстов (простой метод)"""
        from difflib import SequenceMatcher
        return SequenceMatcher(None, text1, text2).ratio()

    def _create_advanced_prompt(
        self,
        task_description: str,
        task_type: str,
        checking_criteria: str,
        recognized_text: str
    ) -> str:
        """Создание детального промпта для GPT-4"""

        return f"""
        Проверь работу ученика по фотографии.
        
        ЗАДАНИЕ:
        {task_description}
        
        ТИП ЗАДАНИЯ: {task_type}
        
        КРИТЕРИИ ОЦЕНКИ:
        {checking_criteria}
        
        РАСПОЗНАННЫЙ ТЕКСТ (может быть неполным):
        {recognized_text}
        
        ИНСТРУКЦИИ:
        1. Внимательно изучи фотографию работы
        2. Оцени правильность решения/ответа
        3. Проверь полноту раскрытия темы
        4. Оцени оформление и читаемость
        5. Дай конструктивную обратную связь
        
        Верни результат в формате JSON:
        {{
            "score": 0-100,
            "feedback": "общая оценка работы",
            "detailed_analysis": {{
                "правильные_моменты": ["список правильных элементов"],
                "ошибки": ["список ошибок с пояснениями"],
                "оформление": "оценка оформления",
                "полнота": "насколько полно раскрыта тема",
                "рекомендации": ["что можно улучшить"]
            }},
            "confidence": 0.0-1.0,
            "suggestions": ["конкретные советы ученику"]
        }}
        """

    def _validate_ai_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Валидация и нормализация ответа AI"""

        # Проверяем обязательные поля
        required_fields = ["score", "feedback", "detailed_analysis"]
        for field in required_fields:
            if field not in response:
                response[field] = self._get_default_value(field)

        # Нормализуем score
        response["score"] = max(0, min(100, float(response.get("score", 0))))

        # Добавляем confidence если нет
        if "confidence" not in response:
            response["confidence"] = 0.8

        # Добавляем suggestions если нет
        if "suggestions" not in response:
            response["suggestions"] = []

        return response

    def _get_default_value(self, field: str) -> Any:
        """Значения по умолчанию для полей"""
        defaults = {
            "score": 50,
            "feedback": "Не удалось полностью проанализировать работу",
            "detailed_analysis": {},
            "confidence": 0.5,
            "suggestions": []
        }
        return defaults.get(field, None)

    def _generate_cache_key(self, photo_path: str, task_description: str) -> str:
        """Генерация ключа для кэша"""
        # Читаем первые 1024 байта файла для хеша
        with open(photo_path, 'rb') as f:
            file_hash = hashlib.md5(f.read(1024)).hexdigest()

        task_hash = hashlib.md5(task_description.encode()).hexdigest()

        return f"{file_hash}:{task_hash}"


# Глобальный экземпляр чекера
ai_checker = AIPhotoChecker()