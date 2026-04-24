"""Сервис интеграции с LLM для всех аналитических сценариев."""

from __future__ import annotations

import base64
import json

from openai import OpenAI

from backend.config import settings


type JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
type JsonDict = dict[str, JsonValue]


TEXT_SYSTEM_PROMPT = """Ты — эксперт по конкурентному анализу.
Проанализируй предоставленный текст конкурента и верни структурированный JSON-ответ.

Формат ответа (строго JSON):
{
  "strengths": ["сильная сторона 1", "сильная сторона 2", "..."],
  "weaknesses": ["слабая сторона 1", "слабая сторона 2", "..."],
  "unique_offers": ["уникальное предложение 1", "уникальное предложение 2", "..."],
  "recommendations": ["рекомендация 1", "рекомендация 2", "..."],
  "summary": "Краткое резюме анализа"
}

Важно:
- Каждый массив должен содержать 3-5 пунктов
- Пиши на русском языке
- Будь конкретен и практичен в рекомендациях
- Возвращай только JSON без пояснений
"""


IMAGE_SYSTEM_PROMPT = """Ты — эксперт по визуальному маркетингу и дизайну.
Проанализируй изображение конкурента (баннер, сайт, упаковка, товар) и верни структурированный JSON.

Формат ответа (строго JSON):
{
  "description": "Детальное описание того, что изображено",
  "marketing_insights": ["инсайт 1", "инсайт 2", "..."],
  "visual_style_score": 7,
  "visual_style_analysis": "Анализ визуального стиля конкурента",
  "recommendations": ["рекомендация 1", "рекомендация 2", "..."]
}

Важно:
- visual_style_score от 0 до 16
- Каждый массив должен содержать 3-5 пунктов
- Пиши на русском языке
- Оценивай цветовую палитру, типографику, композицию, UX/UI элементы
- Возвращай только JSON без пояснений
"""

PARSE_SYSTEM_PROMPT = """Ты — аналитик конкурентных сайтов.
Твоя задача: сделать анализ только по фактам из предоставленного текста страницы.

Формат ответа (строго JSON):
{
  "strengths": ["..."],
  "weaknesses": ["..."],
  "unique_offers": ["..."],
  "recommendations": ["..."],
  "summary": "..."
}

Критические правила:
- Запрещено придумывать функции, интеграции, API, языки, тарифы и иные возможности, если их нет в тексте.
- Используй только явные факты из входных данных.
- Если данных недостаточно, укажи это явно:
  - списки могут быть пустыми или короткими (1-2 пункта),
  - в summary напиши, что данных на странице недостаточно для полного вывода.
- Пиши на русском языке.
- Возвращай только JSON без пояснений.
"""


class LLMService:
    """Инкапсулирует обращение к LLM и нормализацию ответов."""

    def __init__(self) -> None:
        """Инициализирует API-клиент LLM.

        Raises:
            RuntimeError: Если не задан ключ `POLZA_AI_API_KEY`.
        """
        if not settings.polza_api_key:
            raise RuntimeError(
                "POLZA_AI_API_KEY не задан. Укажите ключ в .env и перезапустите сервер."
            )
        self.client = OpenAI(
            api_key=settings.polza_api_key,
            base_url=settings.polza_base_url,
        )

    @staticmethod
    def _extract_json(content: str) -> JsonDict:
        """Извлекает JSON-объект из текстового ответа модели.

        Args:
            content: Сырой текст ответа модели.

        Returns:
            Распарсенный JSON-словарь.

        Raises:
            ValueError: Если JSON-объект не найден.
        """
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.startswith("json"):
                content = content[4:].strip()
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("Model response does not contain JSON object")
        return json.loads(content[start : end + 1])

    @staticmethod
    def _to_str_list(value: JsonValue) -> list[str]:
        """Нормализует значение к списку строк.

        Args:
            value: Произвольное JSON-значение.

        Returns:
            Нормализованный список строк.
        """
        if not isinstance(value, list):
            return []
        result: list[str] = []
        for item in value:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    result.append(text)
            elif isinstance(item, dict):
                point = str(item.get("point", "")).strip()
                details = str(item.get("details", "")).strip()
                if point and details:
                    result.append(f"{point}: {details}")
                elif point:
                    result.append(point)
                elif details:
                    result.append(details)
                else:
                    packed = json.dumps(item, ensure_ascii=False)
                    if packed:
                        result.append(packed)
            elif item is not None:
                result.append(str(item))
        return result

    def _normalize_competition_analysis(self, raw: JsonDict) -> JsonDict:
        """Приводит сырой ответ модели к базовой аналитической схеме.

        Args:
            raw: Сырой JSON модели.

        Returns:
            Словарь в формате CompetitionAnalysis.
        """
        return {
            "strengths": self._to_str_list(raw.get("strengths")),
            "weaknesses": self._to_str_list(raw.get("weaknesses")),
            "unique_offers": self._to_str_list(raw.get("unique_offers")),
            "recommendations": self._to_str_list(raw.get("recommendations")),
            "summary": str(raw.get("summary", "") or "").strip(),
        }

    def _chat(self, messages: list[JsonDict]) -> JsonDict:
        """Выполняет единичный запрос в LLM.

        Args:
            messages: Сообщения в формате chat completions.

        Returns:
            Распарсенный JSON-ответ модели.
        """
        response = self.client.chat.completions.create(
            model=settings.llm_model,
            messages=messages,
            temperature=0.2,
            max_tokens=900,
        )
        content = response.choices[0].message.content or "{}"
        return self._extract_json(content)

    def analyze_text(self, competitor_name: str, text: str) -> JsonDict:
        """Анализирует текст конкурента.

        Args:
            competitor_name: Название конкурента.
            text: Текст для анализа.

        Returns:
            Нормализованный аналитический результат.
        """
        raw = self._chat(
            [
                {"role": "system", "content": TEXT_SYSTEM_PROMPT},
                {"role": "user", "content": f"Конкурент: {competitor_name}\n\nТекст:\n{text}"},
            ]
        )
        return self._normalize_competition_analysis(raw)

    def analyze_image(self, competitor_name: str, image_bytes: bytes, filename: str) -> JsonDict:
        """Анализирует изображение конкурента.

        Args:
            competitor_name: Название конкурента.
            image_bytes: Содержимое файла изображения.
            filename: Имя исходного файла.

        Returns:
            Нормализованный аналитический результат.
        """
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        messages = [
            {"role": "system", "content": IMAGE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Конкурент: {competitor_name}. Проанализируй изображение."},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                ],
            },
        ]
        return self._chat(messages)

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 12000) -> list[str]:
        """Делит большой текст на чанки фиксированного размера.

        Args:
            text: Исходный текст.
            chunk_size: Размер одного чанка в символах.

        Returns:
            Список чанков.
        """
        clean = (text or "").strip()
        if not clean:
            return [""]
        return [clean[i : i + chunk_size] for i in range(0, len(clean), chunk_size)]

    def analyze_parsed_content(
        self,
        url: str,
        title: str,
        h1: str,
        first_paragraph: str,
        full_text: str,
    ) -> JsonDict:
        """Анализирует распарсенный контент сайта по схеме map-reduce.

        Args:
            url: URL страницы.
            title: Заголовок страницы.
            h1: Первый заголовок h1.
            first_paragraph: Первый найденный абзац.
            full_text: Полный извлеченный текст страницы.

        Returns:
            Нормализованный аналитический результат.
        """
        clean_text = (full_text or "").strip()
        if len(clean_text) < 200:
            return {
                "strengths": [],
                "weaknesses": [],
                "unique_offers": [],
                "recommendations": [
                    "Проверить доступность и полноту контента страницы (возможно, контент подгружается JS).",
                    "Добавить на страницу явное описание продукта, ценности и ключевых сценариев использования.",
                ],
                "summary": "Данных на странице недостаточно для надежного конкурентного анализа без предположений.",
            }

        chunks = self._chunk_text(clean_text, chunk_size=12000)

        # Этап map: анализируем каждый чанк, чтобы не терять большую часть текста страницы.
        chunk_results: list[JsonDict] = []
        for index, chunk in enumerate(chunks, start=1):
            chunk_results.append(
                self._extract_json(
                    (
                        self.client.chat.completions.create(
                            model=settings.llm_model,
                            messages=[
                                {"role": "system", "content": PARSE_SYSTEM_PROMPT},
                                {
                                    "role": "user",
                                    "content": (
                                        f"Источник: {url}\n"
                                        f"Title: {title}\n"
                                        f"H1: {h1}\n"
                                        f"Первый абзац: {first_paragraph}\n"
                                        f"Чанк {index}/{len(chunks)}:\n{chunk}"
                                    ),
                                },
                            ],
                            temperature=0,
                            max_tokens=700,
                        ).choices[0].message.content
                        or "{}"
                    )
                )
            )

        # Этап reduce: собираем единый итоговый ответ в той же схеме.
        synth_messages = [
            {"role": "system", "content": PARSE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Собери итоговый конкурентный анализ по всем чанкам сайта строго по фактам.\n"
                    f"URL: {url}\nTitle: {title}\nH1: {h1}\nПервый абзац: {first_paragraph}\n\n"
                    f"Результаты по чанкам (JSON):\n{json.dumps(chunk_results, ensure_ascii=False)}"
                ),
            },
        ]
        raw_content = (
            self.client.chat.completions.create(
                model=settings.llm_model,
                messages=synth_messages,
                temperature=0,
                max_tokens=900,
            ).choices[0].message.content
            or "{}"
        )
        raw = self._extract_json(raw_content)
        return self._normalize_competition_analysis(raw)


llm_service = LLMService()
