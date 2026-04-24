"""HTTP-клиент desktop-приложения для работы с backend API."""

from __future__ import annotations

import os
from pathlib import Path

import requests

from backend.config import settings


type JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
type JsonDict = dict[str, JsonValue]
type JsonResponse = JsonDict | list[JsonDict]


class APIClient:
    """Обертка над requests для вызовов backend endpoint-ов."""

    def __init__(self) -> None:
        """Инициализирует базовый URL и timeout запросов."""
        self.base_url = os.getenv("DESKTOP_BACKEND_URL", f"http://{settings.app_host}:{settings.app_port}")
        self.timeout = 120

    def _request(self, method: str, path: str, **kwargs: object) -> JsonResponse:
        """Выполняет HTTP-запрос к backend.

        Args:
            method: HTTP-метод.
            path: Путь endpoint-а.
            **kwargs: Дополнительные параметры requests.

        Returns:
            JSON-ответ или словарь с ошибкой.
        """
        try:
            resp = requests.request(method, f"{self.base_url}{path}", timeout=self.timeout, **kwargs)
            resp.raise_for_status()
            body = resp.json()
            if isinstance(body, dict):
                return body
            if isinstance(body, list) and all(isinstance(item, dict) for item in body):
                return body
            return {"error": "Некорректный формат ответа backend."}
        except requests.exceptions.ConnectionError:
            return {"error": f"Не удалось подключиться к backend: {self.base_url}"}
        except requests.exceptions.Timeout:
            return {"error": "Превышено время ожидания ответа backend."}
        except requests.exceptions.HTTPError as exc:
            try:
                body = resp.json()
                return body if isinstance(body, dict) else {"error": f"HTTP ошибка: {exc}"}
            except Exception:
                return {"error": f"HTTP ошибка: {exc}"}
        except Exception as exc:
            return {"error": str(exc)}

    def health(self) -> bool:
        """Проверяет доступность backend.

        Returns:
            True, если endpoint `/health` доступен.
        """
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def analyze_text(self, text: str) -> JsonDict:
        """Запускает текстовый анализ.

        Args:
            text: Текст для анализа.

        Returns:
            Результат анализа или ошибка.
        """
        return self._request(
            "POST",
            "/analyze/text",
            json={"competitor_name": "desktop", "text": text},
        )

    def analyze_image(self, file_path: str) -> JsonDict:
        """Запускает анализ изображения.

        Args:
            file_path: Путь к файлу изображения.

        Returns:
            Результат анализа или ошибка.
        """
        fp = Path(file_path)
        mime = "image/png" if fp.suffix.lower() == ".png" else "image/jpeg"
        with fp.open("rb") as fh:
            return self._request(
                "POST",
                "/analyze/image",
                data={"competitor_name": "desktop"},
                files={"file": (fp.name, fh, mime)},
            )

    def parse_site(self, url: str) -> JsonDict:
        """Запускает парсинг сайта.

        Args:
            url: URL страницы.

        Returns:
            Результат парсинга и анализа или ошибка.
        """
        return self._request("POST", "/parse/demo", json={"url": url})

    def history(self) -> list[JsonDict]:
        """Получает список истории.

        Returns:
            Список записей истории или пустой список при ошибке.
        """
        data = self._request("GET", "/history")
        return data if isinstance(data, list) else []

    def clear_history(self) -> JsonDict:
        """Очищает историю запросов.

        Returns:
            Статус операции очистки.
        """
        return self._request("DELETE", "/history")


api_client = APIClient()

