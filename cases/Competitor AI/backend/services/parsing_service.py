"""Сервис парсинга веб-страниц и подготовки данных к анализу."""

from __future__ import annotations

from pathlib import Path
import time
import logging

from bs4 import BeautifulSoup
import requests

from backend.config import settings
from backend.services.llm_service import llm_service

logger = logging.getLogger("Competitor AI.parsing")


class ParsingService:
    """Выполняет извлечение контента страницы и передает его в LLM."""

    def __init__(self) -> None:
        """Создает директорию для скриншотов парсинга."""
        self.screenshots_dir = Path(settings.data_dir) / "screenshots"
        self.screenshots_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _wait_for_dynamic_content(driver, timeout_s: int = 15) -> int:
        """Ожидает стабилизацию динамического контента страницы.

        Args:
            driver: Selenium driver.
            timeout_s: Максимальное время ожидания в секундах.

        Returns:
            Длину видимого текста страницы на момент завершения ожидания.
        """
        deadline = time.time() + timeout_s
        last_len = 0
        stable_hits = 0
        while time.time() < deadline:
            text_len = int(
                driver.execute_script(
                    "return (document.body && document.body.innerText) ? document.body.innerText.length : 0;"
                )
                or 0
            )
            if text_len >= 120 and abs(text_len - last_len) <= 30:
                stable_hits += 1
            else:
                stable_hits = 0
            if stable_hits >= 2:
                return text_len
            last_len = text_len
            time.sleep(0.7)
        return last_len

    def parse_with_selenium(
        self,
        url: str,
        wait_timeout_s: int = 15,
        dynamic_timeout_s: int = 15,
        scroll_cycles: int = 1,
    ) -> tuple[str, str, str, str, str | None]:
        """Парсит страницу через Selenium с fallback на requests.

        Args:
            url: URL страницы.
            wait_timeout_s: Таймаут ожидания `document.readyState`.
            dynamic_timeout_s: Таймаут ожидания динамического контента.
            scroll_cycles: Количество циклов прокрутки страницы.

        Returns:
            Кортеж из title, текста, h1, первого абзаца и пути к скриншоту.
        """
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.support.ui import WebDriverWait
        except Exception:
            return self.parse_fallback(url)

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1440,900")
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(30)
        screenshot_path: str | None = None
        try:
            started = time.perf_counter()
            logger.info(
                "selenium parse started: url=%s wait_timeout=%s dynamic_timeout=%s scroll_cycles=%s",
                url,
                wait_timeout_s,
                dynamic_timeout_s,
                scroll_cycles,
            )
            driver.get(url)
            WebDriverWait(driver, wait_timeout_s).until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            # Активируем ленивые блоки и ждем стабилизацию видимого текста.
            for _ in range(max(1, scroll_cycles)):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(0.8)
                driver.execute_script("window.scrollTo(0, 0);")
            dynamic_len = self._wait_for_dynamic_content(driver, timeout_s=dynamic_timeout_s)
            title = driver.title or "No title"
            page_source = driver.page_source
            soup = BeautifulSoup(page_source, "html.parser")
            text = soup.get_text(" ", strip=True)
            h1 = soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else "Не найден"
            first_paragraph = soup.find("p").get_text(" ", strip=True) if soup.find("p") else "Не найден"
            shot = self.screenshots_dir / "parse_demo.png"
            driver.save_screenshot(str(shot))
            screenshot_path = str(shot)
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            logger.info(
                "selenium parse done: url=%s chars=%s h1_found=%s first_p_found=%s dynamic_len=%s elapsed_ms=%s",
                url,
                len(text),
                h1 != "Не найден",
                first_paragraph != "Не найден",
                dynamic_len,
                elapsed_ms,
            )
            return title, text, h1, first_paragraph, screenshot_path
        except Exception as exc:
            logger.info(
                "selenium parse failed, fallback to requests: url=%s error_type=%s",
                url,
                exc.__class__.__name__,
            )
            return self.parse_fallback(url)
        finally:
            driver.quit()

    @staticmethod
    def parse_fallback(url: str) -> tuple[str, str, str, str, str | None]:
        """Парсит страницу через requests/BeautifulSoup.

        Args:
            url: URL страницы.

        Returns:
            Кортеж из title, текста, h1, первого абзаца и `None` для скриншота.
        """
        started = time.perf_counter()
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        title = soup.title.string.strip() if soup.title and soup.title.string else "No title"
        text = soup.get_text(" ", strip=True)
        h1 = soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else "Не найден"
        first_paragraph = soup.find("p").get_text(" ", strip=True) if soup.find("p") else "Не найден"
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        logger.info(
            "requests fallback done: url=%s chars=%s h1_found=%s first_p_found=%s elapsed_ms=%s",
            url,
            len(text),
            h1 != "Не найден",
            first_paragraph != "Не найден",
            elapsed_ms,
        )
        return title, text, h1, first_paragraph, None

    def parse_and_analyze(self, url: str) -> dict:
        """Парсит страницу и выполняет конкурентный анализ контента.

        Args:
            url: URL страницы для обработки.

        Returns:
            Словарь с извлеченными данными страницы и итоговой аналитикой.
        """
        title, full_text, h1, first_paragraph, screenshot_path = self.parse_with_selenium(url)
        if len(full_text) < 1000:
            logger.info(
                "low extracted content detected, retrying selenium with extended wait: url=%s chars=%s",
                url,
                len(full_text),
            )
            title, full_text, h1, first_paragraph, screenshot_path = self.parse_with_selenium(
                url=url,
                wait_timeout_s=25,
                dynamic_timeout_s=25,
                scroll_cycles=2,
            )

        analyzed_chunks = len(llm_service._chunk_text(full_text, chunk_size=12000))
        logger.info("llm analysis started: url=%s chunks=%s chars=%s", url, analyzed_chunks, len(full_text))
        analysis = llm_service.analyze_parsed_content(
            url=url,
            title=title,
            h1=h1,
            first_paragraph=first_paragraph,
            full_text=full_text,
        )
        logger.info("llm analysis done: url=%s strengths=%s weaknesses=%s", url, len(analysis.get("strengths", [])), len(analysis.get("weaknesses", [])))
        return {
            "url": url,
            "title": title,
            "h1": h1,
            "first_paragraph": first_paragraph,
            "screenshot_path": screenshot_path,
            "analyzed_chunks": analyzed_chunks,
            "strengths": analysis.get("strengths", []),
            "weaknesses": analysis.get("weaknesses", []),
            "unique_offers": analysis.get("unique_offers", []),
            "recommendations": analysis.get("recommendations", []),
            "summary": analysis.get("summary", ""),
        }


parsing_service = ParsingService()
