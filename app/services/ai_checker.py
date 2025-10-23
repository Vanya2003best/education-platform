"""
AI сервис для проверки рукописных работ по фотографиям
Использует OCR + GPT-4 Vision для анализа
"""
import base64
import json
import time
from typing import Dict, Any, Optional
from io import BytesIO
from PIL import Image
import pytesseract
from openai import OpenAI
import os

from app.config import settings


class AIPhotoChecker:
    """Проверка рукописных работ через анализ фотографий"""

    def __init__(self):
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None

    async def check_photo_submission(
            self,
            photo_path: str,
            task_description: str,
            task_type: str,
            checking_criteria: str
    ) -> Dict[str, Any]:
        """
        Главный метод проверки фотографии работы

        Args:
            photo_path: путь к фотографии
            task_description: описание задания
            task_type: тип задания (math, essay, physics и т.д.)
            checking_criteria: критерии проверки (JSON)

        Returns:
            Dict с результатами проверки
        """
        start_time = time.time()

        try:
            # Шаг 1: OCR - распознаем текст
            recognized_text = await self._ocr_image(photo_path)

            # Шаг 2: AI анализ через GPT-4 Vision
            if self.client:
                ai_result = await self._analyze_with_gpt4_vision(
                    photo_path=photo_path,
                    recognized_text=recognized_text,
                    task_description=task_description,
                    task_type=task_type,
                    checking_criteria=checking_criteria
                )
            else:
                # Fallback - базовый анализ без GPT-4
                ai_result = await self._basic_analysis(
                    recognized_text=recognized_text,
                    task_description=task_description
                )

            processing_time = time.time() - start_time

            return {
                "recognized_text": recognized_text,
                "score": ai_result["score"],
                "feedback": ai_result["feedback"],
                "detailed_analysis": ai_result["detailed_analysis"],
                "processing_time": processing_time,
                "status": "checked"
            }

        except Exception as e:
            return {
                "recognized_text": "",
                "score": 0,
                "feedback": f"Ошибка при проверке: {str(e)}",
                "detailed_analysis": {},
                "processing_time": time.time() - start_time,
                "status": "failed"
            }

    async def _ocr_image(self, photo_path: str) -> str:
        """Распознавание текста с фотографии (OCR)"""
        try:
            # Открываем изображение
            image = Image.open(photo_path)

            # Предобработка изображения для лучшего распознавания
            image = self._preprocess_image(image)

            # OCR через Tesseract (поддержка русского и английского)
            text = pytesseract.image_to_string(image, lang='rus+eng')

            return text.strip()
        except Exception as e:
            print(f"OCR Error: {e}")
            return ""

    def _preprocess_image(self, image: Image.Image) -> Image.Image:
        """Предобработка изображения для улучшения OCR"""
        # Конвертируем в grayscale
        image = image.convert('L')

        # Увеличиваем контраст
        from PIL import ImageEnhance
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(2.0)

        return image

    async def _analyze_with_gpt4_vision(
            self,
            photo_path: str,
            recognized_text: str,
            task_description: str,
            task_type: str,
            checking_criteria: str
    ) -> Dict[str, Any]:
        """Анализ работы через GPT-4 Vision"""

        # Кодируем изображение в base64
        with open(photo_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')

        # Формируем промпт для GPT-4
        prompt = self._create_checking_prompt(
            task_description=task_description,
            task_type=task_type,
            checking_criteria=checking_criteria,
            recognized_text=recognized_text
        )

        try:
            # Запрос к GPT-4 Vision
            response = self.client.chat.completions.create(
                model="gpt-4o",  # или gpt-4-vision-preview
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=1500,
                temperature=0.3  # Низкая температура для объективности
            )

            # Парсим ответ
            result_text = response.choices[0].message.content

            # Пытаемся извлечь структурированные данные
            analysis = self._parse_gpt_response(result_text)

            return analysis

        except Exception as e:
            print(f"GPT-4 Vision Error: {e}")
            return {
                "score": 0,
                "feedback": "Не удалось выполнить AI-анализ",
                "detailed_analysis": {}
            }

    def _create_checking_prompt(
            self,
            task_description: str,
            task_type: str,
            checking_criteria: str,
            recognized_text: str
    ) -> str:
        """Создание промпта для GPT-4"""

        prompt = f"""Ты - опытный учитель, проверяющий работу ученика.

ЗАДАНИЕ:
{task_description}

ТИП ЗАДАНИЯ: {task_type}

КРИТЕРИИ ОЦЕНКИ:
{checking_criteria}

РАСПОЗНАННЫЙ ТЕКСТ (OCR):
{recognized_text}

ИНСТРУКЦИЯ:
1. Внимательно изучи фотографию работы ученика
2. Проверь правильность решения согласно критериям
3. Оцени работу по шкале 0-100
4. Дай развернутый feedback с указанием ошибок и правильных моментов

ФОРМАТ ОТВЕТА (JSON):
{{
    "score": <число 0-100>,
    "feedback": "<короткая общая оценка>",
    "detailed_analysis": {{
        "правильные_моменты": ["список правильных элементов"],
        "ошибки": ["список ошибок с объяснениями"],
        "рекомендации": ["что улучшить"],
        "оценка_оформления": "<качество почерка и оформления>",
        "полнота_решения": "<насколько полно раскрыто>"
    }}
}}

Ответь строго в формате JSON!"""

        return prompt

    def _parse_gpt_response(self, response_text: str) -> Dict[str, Any]:
        """Парсинг ответа GPT в структурированный формат"""
        try:
            # Ищем JSON в ответе
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1

            if json_start != -1 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                result = json.loads(json_str)
                return result
            else:
                # Если JSON не найден, возвращаем базовую структуру
                return {
                    "score": 50,
                    "feedback": response_text,
                    "detailed_analysis": {}
                }
        except json.JSONDecodeError:
            return {
                "score": 50,
                "feedback": response_text,
                "detailed_analysis": {}
            }

    async def _basic_analysis(
            self,
            recognized_text: str,
            task_description: str
    ) -> Dict[str, Any]:
        """Базовый анализ без GPT-4 (fallback)"""

        # Простая эвристика
        score = 0
        feedback_parts = []

        # Проверяем, что текст распознан
        if len(recognized_text) > 20:
            score += 30
            feedback_parts.append("✅ Работа содержит текст")
        else:
            feedback_parts.append("❌ Текст не распознан или работа пустая")

        # Проверяем длину
        if len(recognized_text) > 100:
            score += 20
            feedback_parts.append("✅ Достаточный объем работы")

        # Проверяем наличие ключевых слов из задания
        task_words = set(task_description.lower().split())
        text_words = set(recognized_text.lower().split())
        common_words = task_words & text_words

        if len(common_words) > 3:
            score += 30
            feedback_parts.append(f"✅ Работа связана с заданием ({len(common_words)} общих слов)")

        score += 20  # Бонус за попытку

        return {
            "score": min(score, 100),
            "feedback": "\n".join(feedback_parts),
            "detailed_analysis": {
                "текст_распознан": len(recognized_text) > 0,
                "длина_текста": len(recognized_text),
                "общих_слов_с_заданием": len(common_words)
            }
        }


# Глобальный экземпляр чекера
checker = AIPhotoChecker()