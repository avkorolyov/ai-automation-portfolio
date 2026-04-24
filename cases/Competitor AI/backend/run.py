"""Точка запуска Uvicorn для backend-приложения."""

from __future__ import annotations

import socket
import sys
from pathlib import Path
import uvicorn

# Поддерживаем запуск как `python backend/run.py` из корня проекта.
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import settings
from backend.main import app


def _is_port_free(host: str, port: int) -> bool:
    """Проверяет доступность TCP-порта на указанном хосте.

    Args:
        host: Адрес хоста для проверки.
        port: Номер порта.

    Returns:
        True, если порт свободен, иначе False.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) != 0


def _pick_runtime_port(host: str, start_port: int, frozen: bool) -> int:
    """Подбирает порт запуска с fallback для frozen-режима.

    Args:
        host: Адрес хоста для проверки.
        start_port: Предпочитаемый порт запуска.
        frozen: Признак запуска из собранного desktop-приложения.

    Returns:
        Выбранный порт для старта сервера.
    """
    if not frozen:
        return start_port
    if _is_port_free(host, start_port):
        return start_port
    for candidate in range(start_port + 1, start_port + 21):
        if _is_port_free(host, candidate):
            print(f"[WARN] Port {start_port} is busy, fallback to {candidate}")
            return candidate
    return start_port


if __name__ == "__main__":
    is_frozen = getattr(sys, "frozen", False)
    runtime_port = _pick_runtime_port(settings.app_host, settings.app_port, is_frozen)
    if is_frozen:
        uvicorn.run(
            app,
            host=settings.app_host,
            port=runtime_port,
            reload=False,
        )
    else:
        uvicorn.run(
            "backend.main:app",
            host=settings.app_host,
            port=runtime_port,
            reload=True,
        )
