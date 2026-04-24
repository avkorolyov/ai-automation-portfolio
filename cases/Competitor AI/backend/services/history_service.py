"""Сервис хранения и миграции истории запросов."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.config import settings

HISTORY_VERSION = 2


class HistoryService:
    """Управляет чтением, записью и очисткой `data/history.json`."""

    def __init__(self, history_path: str, max_items: int) -> None:
        """Инициализирует сервис истории.

        Args:
            history_path: Путь к файлу истории.
            max_items: Максимальное число хранимых записей.
        """
        self.history_path = Path(history_path)
        self.max_items = max_items
        if not self.history_path.exists():
            self._write([])

    @staticmethod
    def _is_legacy_list_format(data: object) -> bool:
        """Проверяет, что данные имеют старый list-формат.

        Args:
            data: Сырые прочитанные данные.

        Returns:
            True, если обнаружен legacy-формат.
        """
        return isinstance(data, list)

    def _migrate_if_needed(self, raw: object) -> list[dict]:
        """Мигрирует формат истории к текущей версии при необходимости.

        Args:
            raw: Сырые данные из файла.

        Returns:
            Список элементов истории в актуальном формате.
        """
        if self._is_legacy_list_format(raw):
            items = raw if isinstance(raw, list) else []
            self._write(items)
            return items
        if isinstance(raw, dict):
            items = raw.get("items", [])
            if not isinstance(items, list):
                items = []
            version = raw.get("version")
            if version != HISTORY_VERSION:
                self._write(items)
            return items
        self._write([])
        return []

    def _read(self) -> list[dict]:
        """Читает историю из файла и выполняет миграцию формата.

        Returns:
            Список элементов истории.
        """
        if not self.history_path.exists():
            return []
        with self.history_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        return self._migrate_if_needed(raw)

    def _write(self, data: list[dict]) -> None:
        """Записывает историю в файл в текущем формате.

        Args:
            data: Список элементов истории.
        """
        payload = {"version": HISTORY_VERSION, "items": data}
        with self.history_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def add(self, source: str, payload: dict) -> None:
        """Добавляет запись в историю.

        Args:
            source: Источник действия (тип endpoint-а).
            payload: Полезная нагрузка с input/result.
        """
        data = self._read()
        data.append(
            {
                "source": source,
                "payload": payload,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        data = data[-self.max_items :]
        self._write(data)

    def list(self) -> list[dict]:
        """Возвращает текущий список записей истории.

        Returns:
            Список элементов истории.
        """
        return self._read()

    def clear(self) -> None:
        """Очищает историю, сохраняя служебную структуру файла."""
        self._write([])


history_service = HistoryService(
    history_path=settings.history_path,
    max_items=settings.max_history_items,
)
