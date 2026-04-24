"""E2E-проверка web UI через Selenium."""

from __future__ import annotations

import json
import os
import sys
from typing import Callable

import requests
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait


APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = os.getenv("APP_PORT", "8000")


def resolve_base_url() -> str:
    """Определяет рабочий base URL backend по health-check."""
    candidates = [APP_PORT, "8000", "8010", "8020"]
    seen: set[str] = set()
    for port in candidates:
        if port in seen:
            continue
        seen.add(port)
        base = f"http://{APP_HOST}:{port}"
        try:
            response = requests.get(f"{base}/health", timeout=2)
            if response.status_code == 200:
                return base
        except requests.RequestException:
            continue
    raise RuntimeError("Backend is not reachable on expected ports (APP_PORT/8000/8010/8020)")


def check(wait: WebDriverWait, condition: Callable[[], bool], message: str) -> None:
    """Проверяет произвольное условие и выбрасывает ошибку при провале."""
    if not condition():
        raise RuntimeError(message)


def main() -> None:
    """Запускает базовый E2E-сценарий пользовательского интерфейса."""
    base = resolve_base_url()
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1440,900")

    summary = {
        "ui_loaded": 0,
        "menu_switch": 0,
        "text_validation": 0,
        "parse_flow": 0,
        "history_open": 0,
    }

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 25)

    try:
        driver.get(base)
        wait.until(ec.presence_of_element_located((By.CSS_SELECTOR, "main.app")))
        summary["ui_loaded"] += 1

        check(
            wait,
            lambda: "Мониторинг конкурентов" in driver.find_element(By.CSS_SELECTOR, ".page-head h1").text,
            "Main page title is not rendered",
        )

        # Переключение в таб "Анализ текста" и валидация короткого текста.
        text_tab = driver.find_element(By.CSS_SELECTOR, '[data-tab="textTab"]')
        text_tab.click()
        wait.until(ec.presence_of_element_located((By.ID, "txtInput")))
        driver.find_element(By.ID, "txtInput").clear()
        driver.find_element(By.ID, "txtInput").send_keys("коротко")
        driver.find_element(By.ID, "btnText").click()
        wait.until(ec.presence_of_element_located((By.ID, "output")))
        check(
            wait,
            lambda: "минимум 20 символов" in driver.find_element(By.ID, "output").text,
            "Client-side short text validation is not shown",
        )
        summary["text_validation"] += 1

        # Переключение в таб "Парсинг сайта" и позитивный запрос.
        parse_tab = driver.find_element(By.CSS_SELECTOR, '[data-tab="parseTab"]')
        parse_tab.click()
        wait.until(ec.presence_of_element_located((By.ID, "parseUrl")))
        parse_input = driver.find_element(By.ID, "parseUrl")
        parse_input.clear()
        parse_input.send_keys("https://example.com")
        driver.find_element(By.ID, "btnParse").click()
        wait.until(lambda d: "Сайт (карточка страницы)" in d.find_element(By.ID, "output").text)
        summary["parse_flow"] += 1
        summary["menu_switch"] += 1

        # Открытие вкладки истории и отображение списка.
        history_tab = driver.find_element(By.CSS_SELECTOR, '[data-tab="historyTab"]')
        history_tab.click()
        wait.until(ec.presence_of_element_located((By.ID, "historyList")))
        if driver.find_element(By.ID, "historyList").text.strip() == "":
            raise RuntimeError("History list is empty in UI after parse flow")
        summary["history_open"] += 1

        print(json.dumps({"status": "ok", "suite": "e2e_ui", "checked": summary}, ensure_ascii=False))
    except TimeoutException as exc:
        raise RuntimeError(f"E2E timeout: {exc}") from exc
    finally:
        driver.quit()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
