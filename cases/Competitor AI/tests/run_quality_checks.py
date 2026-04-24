"""Единый запуск тестового контура проекта."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def run_step(script_name: str) -> dict:
    """Запускает отдельный тестовый шаг как дочерний процесс.

    Args:
        script_name: Имя python-скрипта в директории `tests`.

    Returns:
        Словарь с результатом выполнения шага.

    Raises:
        RuntimeError: Если скрипт завершился с ошибкой.
    """
    script_path = ROOT / script_name
    if not script_path.exists():
        raise RuntimeError(f"Missing test script: {script_name}")

    process = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        message = process.stderr.strip() or process.stdout.strip() or f"Step failed: {script_name}"
        raise RuntimeError(f"{script_name}: {message}")

    output = process.stdout.strip()
    if not output:
        return {"script": script_name, "status": "ok"}

    for line in reversed(output.splitlines()):
        line = line.strip()
        if not line:
            continue
        if line.startswith("{") and line.endswith("}"):
            try:
                payload = json.loads(line)
                payload["script"] = script_name
                return payload
            except json.JSONDecodeError:
                continue
    return {"script": script_name, "status": "ok", "raw_output": output}


def main() -> None:
    """Запускает общий тест-пайплайн проекта."""
    steps = [
        "smoke_check.py",
        "fullscale_check.py",
        "contract_api_check.py",
        "resilience_check.py",
        "security_check.py",
        "e2e_ui_check.py",
    ]
    results: list[dict] = []
    for step in steps:
        results.append(run_step(step))
    print(json.dumps({"status": "ok", "pipeline": "quality_checks", "steps": results}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
