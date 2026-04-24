"""Desktop GUI-оболочка Competitor AI на базе PyQt6."""

from __future__ import annotations

import os
import sys
from PyQt6.QtCore import QLibraryInfo, QLocale, QSettings, QTimer, QTranslator, QUrl
from pathlib import Path
from PyQt6.QtGui import QAction, QIcon, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedLayout,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from requests import RequestException, get
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeyEvent

APP_VERSION = "1.0.0"
HEADER_TITLE_STYLE = (
    "font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;"
    "font-size:28px; font-weight:700; color:#1c2440; background:transparent;"
)
HEADER_SUBTITLE_STYLE = (
    "font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;"
    "font-size:16px; color:#59668f; background:transparent;"
)


class MainWindow(QMainWindow):
    """Главное окно desktop-клиента с web-вкладками и настройками."""

    @staticmethod
    def _make_header_title(text: str) -> QLabel:
        """Создает заголовок для экранов настроек.

        Args:
            text: Текст заголовка.

        Returns:
            Настроенный QLabel.
        """
        label = QLabel(text)
        label.setStyleSheet(HEADER_TITLE_STYLE)
        return label

    @staticmethod
    def _make_header_subtitle(text: str) -> QLabel:
        """Создает подзаголовок для экранов настроек.

        Args:
            text: Текст подзаголовка.

        Returns:
            Настроенный QLabel.
        """
        label = QLabel(text)
        label.setStyleSheet(HEADER_SUBTITLE_STYLE)
        return label

    def __init__(self) -> None:
        """Инициализирует главное окно и базовую навигацию приложения."""
        super().__init__()
        self.setWindowTitle("Мониторинг конкурентов")
        self.resize(1200, 820)
        self.settings = QSettings("CompetitorAI", "Desktop")
        env_url = os.getenv("DESKTOP_BACKEND_URL", "").strip()
        saved_url = self.settings.value("server_url", "", str).strip()
        self.base_url = env_url or saved_url or "http://127.0.0.1:8010"
        self._loaded_url = ""
        self._web_ready_once = False
        self.settings_dialog: QDialog | None = None

        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setFixedWidth(230)
        sidebar.setStyleSheet("background:#0f1730; color:#d8e2ff;")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(16, 20, 16, 16)
        sidebar_layout.setSpacing(10)

        brand_row = QHBoxLayout()
        brand = QLabel("Competitor AI")
        brand.setStyleSheet("font-size:22px; font-weight:700; color:#ffffff;")
        brand_icon = QLabel()
        pix = QPixmap(_resource_path("brand-icon.png"))
        if not pix.isNull():
            brand_icon.setPixmap(pix.scaled(30, 30))
        else:
            brand_icon.setText("◉")
            brand_icon.setStyleSheet("color:#38bdf8; font-size:18px;")
        brand_row.addWidget(brand_icon)
        brand_row.addWidget(brand)
        brand_row.addStretch(1)
        sidebar_layout.addLayout(brand_row)

        self.btn_text = QPushButton("📝 Анализ текста")
        self.btn_text.clicked.connect(lambda: self.show_web_tab("textTab"))
        self.btn_text.setStyleSheet(self._menu_btn_style(active=True))
        sidebar_layout.addWidget(self.btn_text)

        self.btn_image = QPushButton("🖼️ Анализ изображения")
        self.btn_image.clicked.connect(lambda: self.show_web_tab("imageTab"))
        self.btn_image.setStyleSheet(self._menu_btn_style(active=False))
        sidebar_layout.addWidget(self.btn_image)

        self.btn_pdf = QPushButton("📄 Анализ PDF")
        self.btn_pdf.clicked.connect(lambda: self.show_web_tab("pdfTab"))
        self.btn_pdf.setStyleSheet(self._menu_btn_style(active=False))
        sidebar_layout.addWidget(self.btn_pdf)

        self.btn_parse = QPushButton("🌐 Парсинг сайта")
        self.btn_parse.clicked.connect(lambda: self.show_web_tab("parseTab"))
        self.btn_parse.setStyleSheet(self._menu_btn_style(active=False))
        sidebar_layout.addWidget(self.btn_parse)

        self.btn_history = QPushButton("🕘 История")
        self.btn_history.clicked.connect(lambda: self.show_web_tab("historyTab"))
        self.btn_history.setStyleSheet(self._menu_btn_style(active=False))
        sidebar_layout.addWidget(self.btn_history)

        sidebar_layout.addStretch(1)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color:#263560;")
        sidebar_layout.addWidget(divider)

        self.btn_settings = QPushButton("⚙️ Настройки")
        self.btn_settings.clicked.connect(self.show_settings_page)
        self.btn_settings.setStyleSheet(self._menu_btn_style(active=False))
        sidebar_layout.addWidget(self.btn_settings)

        layout.addWidget(sidebar)

        self.content_host = QWidget()
        self.content_stack = QStackedLayout(self.content_host)
        layout.addWidget(self.content_host, 1)
        self.loading_page = self._build_loading_page()
        self.content_stack.addWidget(self.loading_page)
        self.web = QWebEngineView()
        self.web.loadFinished.connect(self._on_web_load_finished)
        self.content_stack.addWidget(self.web)
        self.content_stack.setCurrentWidget(self.loading_page)

        self.settings_page = self._build_settings_page()
        self.settings_page.hide()
        self.content_stack.addWidget(self.settings_page)
        self._build_app_menu()

        self.load_app()
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self._poll_status_if_visible)
        self.poll_timer.start(5000)

    def _build_loading_page(self) -> QWidget:
        """Создает экран ожидания загрузки web-интерфейса.

        Returns:
            Виджет страницы загрузки.
        """
        page = QWidget()
        page.setStyleSheet("background:#eef2ff;")
        wrap = QVBoxLayout(page)
        wrap.setContentsMargins(24, 24, 24, 24)
        wrap.addStretch(1)
        title = QLabel("Загрузка интерфейса...")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:18px; font-weight:700; color:#1f2937;")
        wrap.addWidget(title)
        wrap.addStretch(1)
        return page

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Обрабатывает клавиатурные шорткаты в web-view.

        Args:
            event: Событие нажатия клавиши.
        """
        # Поддерживаем стандартные Command-шорткаты в EN/RU раскладках.
        if event.modifiers() & Qt.KeyboardModifier.MetaModifier:
            key = event.key()
            text = (event.text() or "").lower()

            if key == Qt.Key.Key_C or text == "с":
                self.web.triggerPageAction(QWebEngineView.WebAction.Copy)
                return
            if key == Qt.Key.Key_V or text == "м":
                self.web.triggerPageAction(QWebEngineView.WebAction.Paste)
                return
            if key == Qt.Key.Key_X or text == "ч":
                self.web.triggerPageAction(QWebEngineView.WebAction.Cut)
                return
            if key == Qt.Key.Key_A or text == "ф":
                self.web.triggerPageAction(QWebEngineView.WebAction.SelectAll)
                return
            if key == Qt.Key.Key_Z or text == "я":
                self.web.triggerPageAction(QWebEngineView.WebAction.Undo)
                return
            if key == Qt.Key.Key_Y or text == "н":
                self.web.triggerPageAction(QWebEngineView.WebAction.Redo)
                return

        super().keyPressEvent(event)

    @staticmethod
    def _menu_btn_style(active: bool) -> str:
        """Возвращает CSS-стиль кнопки меню.

        Args:
            active: Признак активной вкладки.

        Returns:
            Строка со стилем QPushButton.
        """
        bg = "#2a3f8a" if active else "transparent"
        border = "#405fcb" if active else "transparent"
        color = "#ffffff" if active else "#c4d2ff"
        return (
            "QPushButton {"
            f"background:{bg}; color:{color}; border:1px solid {border};"
            "padding:10px 12px; border-radius:10px; text-align:left;"
            "}"
            "QPushButton:hover { background:#1b2852; color:#ffffff; }"
        )

    def _set_active_menu(self, active: str) -> None:
        """Обновляет визуальное состояние кнопок бокового меню.

        Args:
            active: Идентификатор активной вкладки.
        """
        self.btn_text.setStyleSheet(self._menu_btn_style(active=active == "textTab"))
        self.btn_image.setStyleSheet(self._menu_btn_style(active=active == "imageTab"))
        self.btn_pdf.setStyleSheet(self._menu_btn_style(active=active == "pdfTab"))
        self.btn_parse.setStyleSheet(self._menu_btn_style(active=active == "parseTab"))
        self.btn_history.setStyleSheet(self._menu_btn_style(active=active == "historyTab"))
        self.btn_settings.setStyleSheet(self._menu_btn_style(active=active == "settings"))

    def _build_app_menu(self) -> None:
        """Формирует верхнее системное меню приложения."""
        menu = self.menuBar().addMenu("Competitor AI")
        about = QAction("О программе", self)
        about.setMenuRole(QAction.MenuRole.AboutRole)
        about.triggered.connect(self.show_about)
        menu.addAction(about)

        prefs = QAction("Настройки", self)
        prefs.setMenuRole(QAction.MenuRole.PreferencesRole)
        prefs.triggered.connect(self.show_settings_page)
        menu.addAction(prefs)

    def _build_settings_page(self) -> QWidget:
        """Создает встроенную страницу настроек.

        Returns:
            Виджет страницы настроек.
        """
        page = QWidget()
        page.setStyleSheet("background:#eef2ff;")
        wrap = QVBoxLayout(page)
        wrap.setContentsMargins(24, 24, 24, 24)
        wrap.setSpacing(0)

        title = self._make_header_title("Мониторинг конкурентов")
        subtitle = self._make_header_subtitle("AI-ассистент для анализа конкурентной среды")
        wrap.addWidget(title)
        wrap.addSpacing(6)
        wrap.addWidget(subtitle)
        wrap.addSpacing(14)

        section = QLabel("Настройки")
        section.setStyleSheet("font-size:20px; font-weight:700; color:#1f2937; margin:0; background:transparent;")
        card = QFrame()
        card.setObjectName("settingsCard")
        card.setStyleSheet(
            "QFrame#settingsCard {"
            "background:#ffffff; border:1px solid #e2e8f0; border-radius:16px;"
            "}"
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(14)
        wrap.addWidget(card)
        card_layout.addWidget(section)

        server_label = QLabel("Адрес сервера Competitor AI")
        server_label.setStyleSheet("background:transparent; color:#4f5f8d; font-size:13px; font-weight:600;")
        self.server_input = QLineEdit(self.base_url)
        self.server_input.setStyleSheet(
            "QLineEdit {"
            "background:#ffffff;"
            "border:1px solid #d7dff2;"
            "border-radius:10px;"
            "padding:11px 12px;"
            "color:#1c2440;"
            "}"
            "QLineEdit:focus { border:1px solid #5b7cff; }"
        )
        card_layout.addWidget(server_label)
        card_layout.addWidget(self.server_input)

        status_row = QHBoxLayout()
        status_title = QLabel("Статус сервера")
        status_title.setStyleSheet("background:transparent; color:#4f5f8d; font-size:13px; font-weight:600;")
        self.connection_label = QLabel("Проверка подключения...")
        self.connection_label.setMinimumHeight(22)
        self.connection_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.connection_label.setStyleSheet(
            "background:transparent; color:#475569; padding:0; font-weight:600;"
        )
        status_row.addWidget(status_title)
        status_row.addWidget(self.connection_label)
        status_row.addStretch(1)
        card_layout.addLayout(status_row)

        actions = QHBoxLayout()
        save_btn = QPushButton("Сохранить")
        test_btn = QPushButton("Проверить")
        save_btn.setStyleSheet(
            "QPushButton { background:#3c62ff; color:#fff; border:0; border-radius:10px; padding:10px 14px; }"
            "QPushButton:hover { background:#2f52ea; }"
        )
        test_btn.setStyleSheet(
            "QPushButton { background:#3c62ff; color:#fff; border:0; border-radius:10px; padding:10px 14px; }"
            "QPushButton:hover { background:#2f52ea; }"
        )
        save_btn.clicked.connect(self.save_settings)
        test_btn.clicked.connect(self.refresh_status)
        actions.addWidget(save_btn)
        actions.addWidget(test_btn)
        actions.addStretch(1)
        card_layout.addLayout(actions)
        wrap.addSpacing(14)
        wrap.addStretch(1)
        return page

    def _is_backend_alive(self) -> bool:
        """Проверяет доступность backend endpoint-а `/health`.

        Returns:
            True, если backend доступен.
        """
        try:
            resp = get(f"{self.base_url}/health", timeout=1.5)
            return resp.status_code == 200
        except RequestException:
            return False

    def _poll_status_if_visible(self) -> None:
        """Периодически обновляет статус backend в открытом окне настроек."""
        if self.settings_dialog and self.settings_dialog.isVisible():
            self.refresh_status()

    def load_app(self) -> None:
        """Загружает web-интерфейс или показывает заглушку недоступности backend."""
        alive = self._is_backend_alive()
        if alive:
            if self._loaded_url != self.base_url:
                self.web.setUrl(QUrl(self.base_url))
                self._loaded_url = self.base_url
            self.connection_label.setText("Online")
            self.connection_label.setStyleSheet(
                "background:transparent; color:#166534; padding:0; font-weight:700;"
            )
        else:
            self.connection_label.setText("Offline")
            self.connection_label.setStyleSheet(
                "background:transparent; color:#991b1b; padding:0; font-weight:700;"
            )
            html = (
                "<html><body style='font-family: Inter, sans-serif; padding: 24px;'>"
                "<h2>Backend недоступен</h2>"
                f"<p>Не удалось открыть <b>{self.base_url}</b>.</p>"
                "<p>Запустите backend командой: <code>python backend/run.py</code>, затем нажмите "
                "<b>Сохранить</b> или <b>Проверить</b> в настройках.</p>"
                "</body></html>"
            )
            self.web.setHtml(html)
            self._loaded_url = ""

    def _apply_embedded_layout(self) -> None:
        """Скрывает web-сайдбар и адаптирует layout под desktop-оболочку."""
        js = """
        (() => {
          const styleId = 'desktop-embed-overrides';
          if (!document.getElementById(styleId)) {
            const st = document.createElement('style');
            st.id = styleId;
            st.textContent = `
              .app { grid-template-columns: 1fr !important; background: #eef2ff !important; }
              .sidebar { display: none !important; }
              .content { max-width: none !important; width: 100% !important; padding: 24px !important; }
            `;
            document.head.appendChild(st);
          }
          const sidebar = document.querySelector('.sidebar');
          if (sidebar) sidebar.style.display = 'none';
          const app = document.querySelector('.app');
          if (app) {
            app.style.gridTemplateColumns = '1fr';
            app.style.background = '#eef2ff';
          }
          const content = document.querySelector('.content');
          if (content) {
            content.style.maxWidth = 'none';
            content.style.width = '100%';
          }
        })();
        """
        self.web.page().runJavaScript(js)

    def _on_web_load_finished(self, ok: bool) -> None:
        """Обрабатывает событие завершения загрузки web-страницы.

        Args:
            ok: Флаг успешной загрузки страницы.
        """
        if ok:
            self._apply_embedded_layout()
            self._web_ready_once = True
        # Даже при ошибке загрузки нужно выйти с экрана ожидания.
        self.content_stack.setCurrentWidget(self.web)

    def _switch_web_tab(self, tab_id: str) -> None:
        """Переключает вкладку внутри встроенного web-интерфейса.

        Args:
            tab_id: Идентификатор целевой вкладки.
        """
        js = f"""
        (() => {{
          const btn = document.querySelector(`.menu-btn[data-tab="{tab_id}"]`);
          if (btn) btn.click();
        }})();
        """
        self.web.page().runJavaScript(js)

    def refresh_status(self) -> None:
        """Обновляет индикатор статуса подключения к backend."""
        # Избегаем лишнего обновления стилей, чтобы периодический опрос оставался легким.
        self.base_url = self.server_input.text().strip() or self.base_url
        alive = self._is_backend_alive()
        if alive:
            if self.connection_label.text() != "Online":
                self.connection_label.setText("Online")
                self.connection_label.setStyleSheet(
                    "background:transparent; color:#166534; padding:0; font-weight:700;"
                )
        else:
            if self.connection_label.text() != "Offline":
                self.connection_label.setText("Offline")
                self.connection_label.setStyleSheet(
                    "background:transparent; color:#991b1b; padding:0; font-weight:700;"
                )

    def save_settings(self) -> None:
        """Сохраняет настройки backend URL и перезагружает web-часть."""
        new_url = self.server_input.text().strip()
        if not new_url.startswith(("http://", "https://")):
            QMessageBox.warning(self, "Ошибка", "Адрес должен начинаться с http:// или https://")
            return
        self.base_url = new_url
        self.settings.setValue("server_url", self.base_url)
        self.load_app()
        QMessageBox.information(self, "Сохранено", "Настройки сохранены.")

    def show_web_tab(self, tab_id: str) -> None:
        """Открывает выбранную web-вкладку в desktop-контейнере.

        Args:
            tab_id: Идентификатор вкладки.
        """
        self._set_active_menu(active=tab_id)
        if self._loaded_url != self.base_url:
            self.load_app()
        QTimer.singleShot(0, lambda: self._switch_web_tab(tab_id))

    def show_settings_page(self) -> None:
        """Открывает модальное окно настроек подключения к backend."""
        self._set_active_menu(active="settings")
        dlg = QDialog(self)
        dlg.setWindowTitle("Настройки")
        dlg.setModal(True)
        dlg.setMinimumWidth(640)
        dlg.setStyleSheet("background:#eef2ff;")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        card = QFrame()
        card.setStyleSheet("background:#ffffff; border:1px solid #e2e8f0; border-radius:16px;")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(14)
        layout.addWidget(card)

        section = QLabel("Настройки")
        section.setFrameStyle(QFrame.Shape.NoFrame)
        section.setStyleSheet(
            "font-size:20px; font-weight:700; color:#1f2937; background:transparent; border:0;"
        )
        card_layout.addWidget(section)

        server_label = QLabel("Адрес сервера Competitor AI")
        server_label.setFrameStyle(QFrame.Shape.NoFrame)
        server_label.setStyleSheet(
            "background:transparent; color:#4f5f8d; font-size:13px; font-weight:600; border:0;"
        )
        card_layout.addWidget(server_label)

        self.server_input = QLineEdit(self.base_url)
        self.server_input.setStyleSheet(
            "QLineEdit { background:#ffffff; border:1px solid #d7dff2; border-radius:10px; padding:11px 12px; color:#1c2440; }"
            "QLineEdit:focus { border:1px solid #5b7cff; }"
        )
        card_layout.addWidget(self.server_input)

        status_row = QHBoxLayout()
        status_title = QLabel("Статус сервера")
        status_title.setFrameStyle(QFrame.Shape.NoFrame)
        status_title.setStyleSheet(
            "background:transparent; color:#4f5f8d; font-size:13px; font-weight:600; border:0;"
        )
        self.connection_label = QLabel("Проверка подключения...")
        self.connection_label.setStyleSheet("background:transparent; color:#475569; padding:0; font-weight:600;")
        status_row.addWidget(status_title)
        status_row.addWidget(self.connection_label)
        status_row.addStretch(1)
        card_layout.addLayout(status_row)

        actions = QHBoxLayout()
        save_btn = QPushButton("Сохранить")
        save_btn.setStyleSheet(
            "QPushButton { background:#3c62ff; color:#fff; border:0; border-radius:10px; padding:10px 14px; }"
            "QPushButton:hover { background:#2f52ea; }"
        )
        test_btn = QPushButton("Проверить")
        test_btn.setStyleSheet(
            "QPushButton { background:#3c62ff; color:#fff; border:0; border-radius:10px; padding:10px 14px; }"
            "QPushButton:hover { background:#2f52ea; }"
        )
        save_btn.clicked.connect(self.save_settings)
        test_btn.clicked.connect(self.refresh_status)
        actions.addWidget(save_btn)
        actions.addWidget(test_btn)
        actions.addStretch(1)
        card_layout.addLayout(actions)

        self.settings_dialog = dlg
        self.refresh_status()
        dlg.exec()
        self.settings_dialog = None
        self._set_active_menu(active="textTab")

    def show_about(self) -> None:
        """Открывает модальное окно с информацией о приложении."""
        dlg = QDialog(self)
        dlg.setWindowTitle("О программе")
        dlg.setModal(True)
        dlg.setMinimumWidth(380)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        header = QHBoxLayout()
        icon_label = QLabel()
        pix = QPixmap(_resource_path("brand-icon.png"))
        if not pix.isNull():
            icon_label.setPixmap(pix.scaled(28, 28))
        title = QLabel("Competitor AI")
        title.setStyleSheet("font-size:18px; font-weight:700; color:#1f2937;")
        header.addWidget(icon_label)
        header.addWidget(title)
        header.addStretch(1)
        layout.addLayout(header)

        text = QLabel("AI-ассистент для анализа конкурентной среды")
        text.setStyleSheet("color:#334155;")
        layout.addWidget(text)

        version = QLabel(f"Версия: {APP_VERSION}")
        version.setStyleSheet("color:#64748b;")
        layout.addWidget(version)

        ok_row = QHBoxLayout()
        ok_row.addStretch(1)
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(
            "QPushButton { background:#3c62ff; color:#fff; border:0; border-radius:10px; padding:8px 14px; }"
            "QPushButton:hover { background:#2f52ea; }"
        )
        ok_btn.clicked.connect(dlg.accept)
        ok_row.addWidget(ok_btn)
        layout.addLayout(ok_row)

        dlg.exec()


def main() -> None:
    """Запускает desktop-приложение Competitor AI."""
    app = QApplication(sys.argv)
    QLocale.setDefault(QLocale(QLocale.Language.Russian, QLocale.Country.Russia))
    app.setApplicationName("Competitor AI")
    app.setApplicationDisplayName("Competitor AI")
    # Подключаем переводы Qt, чтобы локализовать системные элементы интерфейса.
    tr_base = QTranslator(app)
    tr_widgets = QTranslator(app)
    i18n_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if tr_base.load("qtbase_ru", i18n_path):
        app.installTranslator(tr_base)
    if tr_widgets.load("qt_ru", i18n_path):
        app.installTranslator(tr_widgets)
    app_icon = QIcon(_resource_path("brand-icon.png"))
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)
    w = MainWindow()
    if not app_icon.isNull():
        w.setWindowIcon(app_icon)
    w.show()
    sys.exit(app.exec())


def _resource_path(name: str) -> str:
    """Разрешает путь к ресурсу в dev- и PyInstaller-режиме.

    Args:
        name: Имя файла ресурса.

    Returns:
        Строковый путь к найденному ресурсу.
    """
    # В runtime PyInstaller размещает дополнительные файлы под `_MEIPASS`.
    base_dir = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    candidates = [
        base_dir / name,
        base_dir / "frontend" / name,
        Path(__file__).resolve().parents[1] / "frontend" / name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return str(candidates[-1])


if __name__ == "__main__":
    main()

