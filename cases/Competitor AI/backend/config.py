"""Конфигурация backend и загрузка переменных окружения."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]


def _load_env() -> None:
    """Загружает `.env` из доступных путей запуска приложения."""
    candidates: list[Path] = []

    # Стандартное расположение при локальной разработке.
    candidates.append(ROOT / ".env")
    # Текущая директория запуска (удобно при запуске из корня проекта).
    candidates.append(Path.cwd() / ".env")

    if getattr(sys, "frozen", False):
        exe_path = Path(sys.executable).resolve()
        # Внутри .app: .../Competitor AI.app/Contents/MacOS/Competitor AI
        candidates.append(exe_path.parent / ".env")
        candidates.append(exe_path.parents[2] / ".env")
        candidates.append(exe_path.parents[3] / ".env")

    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if candidate.exists():
            load_dotenv(candidate, override=True)


_load_env()


@dataclass(frozen=True)
class Settings:
    """Контейнер настроек приложения, прочитанных из окружения."""
    app_host: str = os.getenv("APP_HOST", "127.0.0.1")
    app_port: int = int(os.getenv("APP_PORT", "8000"))
    max_history_items: int = int(os.getenv("MAX_HISTORY_ITEMS", "100"))
    history_path: str = str(ROOT / "data" / "history.json")
    data_dir: str = str(ROOT / "data")

    polza_base_url: str = os.getenv("POLZA_BASE_URL", "https://polza.ai/api/v1")
    polza_api_key: str = (os.getenv("POLZA_AI_API_KEY", "") or "").strip()
    llm_model: str = os.getenv("LLM_MODEL", "openai/gpt-4o")

    competitor_urls: tuple[str, ...] = (
        "https://www.melke.ru",
        "https://www.eurookna.ru",
        "https://www.fabrikaokon.ru",
        "https://oknafortaly.ru",
        "https://okna2-0.ru",
    )


settings = Settings()
