"""Общие Qt-стили desktop-приложения."""

from __future__ import annotations

APP_STYLE = """
QMainWindow, QWidget { background: #0f172a; color: #e2e8f0; font-family: Inter, Arial, sans-serif; }
QFrame#card { background: #111827; border: 1px solid #1f2937; border-radius: 10px; }
QPushButton { background: #2563eb; color: #fff; border: none; border-radius: 8px; padding: 10px 14px; }
QPushButton:hover { background: #1d4ed8; }
QLineEdit, QTextEdit { background: #0b1220; border: 1px solid #334155; border-radius: 8px; padding: 8px; color: #e2e8f0; }
QTabWidget::pane { border: none; }
QTabBar::tab { background: #1f2937; padding: 8px 12px; margin-right: 4px; border-radius: 6px; color: #94a3b8; }
QTabBar::tab:selected { background: #2563eb; color: #fff; }
QLabel#title { font-size: 22px; font-weight: 700; }
QLabel#muted { color: #94a3b8; }
"""

