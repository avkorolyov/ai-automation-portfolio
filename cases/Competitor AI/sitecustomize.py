"""Автоподключение coverage для дочерних Python-процессов.

Модуль автоматически импортируется интерпретатором Python (через site.py),
если файл доступен в PYTHONPATH. Это позволяет coverage собирать метрики
из subprocess-запусков в `tests/run_quality_checks.py`.
"""

from __future__ import annotations

try:
    import coverage
except Exception:
    coverage = None

if coverage is not None:
    coverage.process_startup()
