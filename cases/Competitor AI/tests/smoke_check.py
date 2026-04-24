"""Smoke-проверка основных backend endpoint-ов."""

from __future__ import annotations

import json
import mimetypes
import os
import sys
import time
from pathlib import Path

import requests


APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = os.getenv("APP_PORT", "8000")
ROOT = Path(__file__).resolve().parent.parent
TEST_DATA = ROOT / "tests" / "data"


def resolve_base_url() -> str:
    """Определяет рабочий base URL backend по health-check.

    Returns:
        Base URL доступного backend.

    Raises:
        RuntimeError: Если backend недоступен ни на одном ожидаемом порту.
    """
    candidates = [APP_PORT, "8000", "8010"]
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
    raise RuntimeError("Backend is not reachable on expected ports (APP_PORT/8000/8010)")


def assert_ok(response: requests.Response, context: str) -> None:
    """Проверяет, что HTTP-ответ успешен.

    Args:
        response: HTTP-ответ.
        context: Контекст сценария для сообщения об ошибке.

    Raises:
        RuntimeError: Если код ответа >= 400.
    """
    if response.status_code >= 400:
        raise RuntimeError(f"{context} failed: {response.status_code} {response.text[:300]}")


def assert_keys(payload: dict, required: set[str], context: str) -> None:
    """Проверяет наличие обязательных ключей в JSON-ответе.

    Args:
        payload: JSON-объект ответа.
        required: Набор обязательных ключей.
        context: Контекст сценария для сообщения об ошибке.

    Raises:
        RuntimeError: Если отсутствуют обязательные ключи.
    """
    missing = sorted(required - set(payload.keys()))
    if missing:
        raise RuntimeError(f"{context} missing keys: {missing}")


def iter_files(directory: Path, patterns: tuple[str, ...]) -> list[Path]:
    """Собирает список файлов по набору glob-шаблонов.

    Args:
        directory: Директория поиска.
        patterns: Набор glob-шаблонов.

    Returns:
        Отсортированный список файлов.
    """
    files: list[Path] = []
    for pattern in patterns:
        files.extend(directory.glob(pattern))
    return sorted([p for p in files if p.is_file()])


def guess_mime(path: Path, default: str) -> str:
    """Определяет MIME-тип файла по имени.

    Args:
        path: Путь к файлу.
        default: MIME-тип по умолчанию.

    Returns:
        Определенный MIME-тип или `default`.
    """
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or default


def post_with_retry(
    url: str,
    *,
    context: str,
    attempts: int = 3,
    retry_for_statuses: tuple[int, ...] = (502, 503, 504),
    sleep_s: float = 1.0,
    **kwargs: object,
) -> requests.Response:
    """Выполняет POST-запрос с ретраями для нестабильных внешних зависимостей.

    Args:
        url: URL endpoint-а.
        context: Контекст сценария для сообщений об ошибке.
        attempts: Количество попыток.
        retry_for_statuses: Коды, при которых выполняется повтор.
        sleep_s: Пауза между попытками.
        **kwargs: Параметры requests.post.

    Returns:
        Последний успешный или финальный ответ.

    Raises:
        RuntimeError: Если все попытки завершились исключением.
    """
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.post(url, **kwargs)
        except requests.RequestException as exc:
            last_exc = exc
            if attempt == attempts:
                raise RuntimeError(f"{context} request failed after retries: {exc}") from exc
            time.sleep(sleep_s)
            continue
        if response.status_code in retry_for_statuses and attempt < attempts:
            time.sleep(sleep_s)
            continue
        return response
    if last_exc is not None:
        raise RuntimeError(f"{context} request failed: {last_exc}") from last_exc
    raise RuntimeError(f"{context} request failed without response")


def post_file_with_retry(
    url: str,
    *,
    context: str,
    field_name: str,
    file_path: Path,
    mime: str,
    data: dict[str, str],
    timeout: int,
    attempts: int = 3,
    retry_for_statuses: tuple[int, ...] = (502, 503, 504),
    sleep_s: float = 1.0,
) -> requests.Response:
    """Выполняет POST multipart с повторным открытием файла на каждой попытке.

    Args:
        url: URL endpoint-а.
        context: Контекст сценария.
        field_name: Имя multipart-поля файла.
        file_path: Путь к файлу.
        mime: MIME-тип файла.
        data: Form-поля запроса.
        timeout: Таймаут запроса в секундах.
        attempts: Количество попыток.
        retry_for_statuses: Коды, при которых делается повтор.
        sleep_s: Пауза между попытками.

    Returns:
        Ответ последней успешной/финальной попытки.
    """
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            with file_path.open("rb") as handler:
                response = requests.post(
                    url,
                    data=data,
                    files={field_name: (file_path.name, handler, mime)},
                    timeout=timeout,
                )
        except requests.RequestException as exc:
            last_exc = exc
            if attempt == attempts:
                raise RuntimeError(f"{context} request failed after retries: {exc}") from exc
            time.sleep(sleep_s)
            continue
        if response.status_code in retry_for_statuses and attempt < attempts:
            time.sleep(sleep_s)
            continue
        return response
    if last_exc is not None:
        raise RuntimeError(f"{context} request failed: {last_exc}") from last_exc
    raise RuntimeError(f"{context} request failed without response")


def main() -> None:
    """Запускает smoke-проверку всех категорий тестовых данных.

    Raises:
        RuntimeError: При ошибке любого тестового сценария.
    """
    summary: dict[str, int] = {"texts": 0, "urls": 0, "images": 0, "pdfs": 0}
    base = resolve_base_url()

    # Текстовые кейсы: все файлы из tests/data/texts.
    text_files = iter_files(TEST_DATA / "texts", ("*.txt",))
    if not text_files:
        raise RuntimeError("No text files found in tests/data/texts")
    for fp in text_files:
        r = post_with_retry(
            f"{base}/analyze/text",
            context=f"text {fp.name}",
            json={"competitor_name": fp.stem, "text": fp.read_text(encoding="utf-8")},
            timeout=60,
        )
        assert_ok(r, f"text {fp.name}")
        data = r.json()
        assert_keys(data, {"strengths", "weaknesses", "unique_offers", "recommendations", "summary"}, f"text {fp.name}")
        summary["texts"] += 1

    # Парсинг URL: все адреса из tests/data/urls.txt.
    urls_path = TEST_DATA / "urls.txt"
    if not urls_path.exists():
        raise RuntimeError("Missing urls file: tests/data/urls.txt")
    urls = [u.strip() for u in urls_path.read_text(encoding="utf-8").splitlines() if u.strip()]
    if not urls:
        raise RuntimeError("No URLs found in tests/data/urls.txt")
    for url in urls:
        r = post_with_retry(
            f"{base}/parse/demo",
            context=f"parse {url}",
            json={"url": url},
            timeout=360,
        )
        assert_ok(r, f"parse {url}")
        data = r.json()
        assert_keys(
            data,
            {
                "url",
                "title",
                "h1",
                "first_paragraph",
                "screenshot_path",
                "analyzed_chunks",
                "strengths",
                "weaknesses",
                "unique_offers",
                "recommendations",
                "summary",
            },
            f"parse {url}",
        )
        summary["urls"] += 1

    # Анализ изображений: все файлы из tests/data/images.
    image_files = iter_files(TEST_DATA / "images", ("*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp"))
    if not image_files:
        raise RuntimeError("No image files found in tests/data/images")
    for image in image_files:
        mime = guess_mime(image, "image/png")
        r = post_file_with_retry(
            f"{base}/analyze/image",
            context=f"image {image.name}",
            field_name="file",
            file_path=image,
            mime=mime,
            data={"competitor_name": image.stem},
            timeout=60,
        )
        assert_ok(r, f"image {image.name}")
        data = r.json()
        assert_keys(
            data,
            {"description", "marketing_insights", "visual_style_score", "visual_style_analysis", "recommendations"},
            f"image {image.name}",
        )
        summary["images"] += 1

    # Анализ PDF: все файлы из tests/data/pdfs.
    pdf_files = iter_files(TEST_DATA / "pdfs", ("*.pdf",))
    if not pdf_files:
        raise RuntimeError("No PDF files found in tests/data/pdfs")
    for pdf in pdf_files:
        r = post_file_with_retry(
            f"{base}/analyze/pdf",
            context=f"pdf {pdf.name}",
            field_name="file",
            file_path=pdf,
            mime="application/pdf",
            data={"competitor_name": pdf.stem},
            timeout=60,
        )
        assert_ok(r, f"pdf {pdf.name}")
        data = r.json()
        assert_keys(data, {"strengths", "weaknesses", "unique_offers", "recommendations", "summary"}, f"pdf {pdf.name}")
        summary["pdfs"] += 1

    print(json.dumps({"status": "ok", "checked": summary}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
