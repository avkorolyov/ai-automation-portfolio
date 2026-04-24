"""Запуск quality-пайплайна с формальным замером покрытия."""

from __future__ import annotations

import os
import json
import signal
import subprocess
import sys
import time
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parent.parent


def run(command: list[str], env: dict[str, str]) -> None:
    """Запускает команду и завершает процесс при ошибке.

    Args:
        command: Команда с аргументами.
        env: Окружение процесса.
    """
    process = subprocess.run(command, cwd=ROOT, env=env, check=False)
    if process.returncode != 0:
        raise RuntimeError(f"Command failed ({process.returncode}): {' '.join(command)}")


def main() -> None:
    """Выполняет pipeline + coverage combine/report с порогом 80%."""
    env = os.environ.copy()
    env["COVERAGE_PROCESS_START"] = str(ROOT / ".coveragerc")
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["APP_HOST"] = "127.0.0.1"
    env["APP_PORT"] = "8020"

    run([sys.executable, "-m", "coverage", "erase"], env)
    backend_process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "coverage",
            "run",
            "--parallel-mode",
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            env["APP_HOST"],
            "--port",
            env["APP_PORT"],
        ],
        cwd=ROOT,
        env=env,
    )
    try:
        health_url = f"http://{env['APP_HOST']}:{env['APP_PORT']}/health"
        for _ in range(60):
            if backend_process.poll() is not None:
                raise RuntimeError("Backend process exited before health-check")
            try:
                response = requests.get(health_url, timeout=1.5)
                if response.status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.5)
        else:
            raise RuntimeError("Backend did not become healthy on APP_PORT=8020")

        run([sys.executable, "-m", "coverage", "run", "--parallel-mode", "tests/run_quality_checks.py"], env)
    finally:
        if backend_process.poll() is None:
            backend_process.send_signal(signal.SIGINT)
            try:
                backend_process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                backend_process.kill()
                backend_process.wait(timeout=5)

    run([sys.executable, "-m", "coverage", "combine"], env)
    run([sys.executable, "-m", "coverage", "report"], env)
    run([sys.executable, "-m", "coverage", "xml"], env)

    if not (ROOT / "node_modules").exists():
        run(["npm", "install"], env)
    run(["npm", "run", "coverage:frontend"], env)

    summary_path = ROOT / "tests" / "artifacts" / "coverage" / "frontend" / "coverage-summary.json"
    if not summary_path.exists():
        raise RuntimeError("Missing frontend coverage summary file")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    frontend_lines = float(summary.get("total", {}).get("lines", {}).get("pct", 0.0))
    print(f"frontend_coverage_lines_pct={frontend_lines:.2f}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
