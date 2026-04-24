"""Полномасштабная проверка API по расширенному набору сценариев."""

from __future__ import annotations

import json
import mimetypes
import os
import sys
import time
from pathlib import Path

import requests
from PIL import Image, ImageStat


APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = os.getenv("APP_PORT", "8000")
BASE = ""
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "tests" / "data"
FULL = DATA / "fullscale"


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
        context: Контекст проверки.

    Raises:
        RuntimeError: Если код ответа >= 400.
    """
    if response.status_code >= 400:
        raise RuntimeError(f"{context} failed: {response.status_code} {response.text[:300]}")


def assert_error(response: requests.Response, context: str) -> None:
    """Проверяет, что HTTP-ответ завершился ошибкой.

    Args:
        response: HTTP-ответ.
        context: Контекст проверки.

    Raises:
        RuntimeError: Если код ответа < 400.
    """
    if response.status_code < 400:
        raise RuntimeError(f"{context} expected error status, got {response.status_code}")


def assert_keys(payload: dict, required: set[str], context: str) -> None:
    """Проверяет наличие обязательных ключей в JSON.

    Args:
        payload: JSON-объект ответа.
        required: Обязательные ключи.
        context: Контекст проверки.

    Raises:
        RuntimeError: Если отсутствуют обязательные ключи.
    """
    missing = sorted(required - set(payload.keys()))
    if missing:
        raise RuntimeError(f"{context} missing keys: {missing}")


def iter_files(directory: Path, patterns: tuple[str, ...]) -> list[Path]:
    """Собирает файлы по glob-шаблонам.

    Args:
        directory: Директория поиска.
        patterns: Набор шаблонов.

    Returns:
        Отсортированный список файлов.
    """
    found: list[Path] = []
    for pattern in patterns:
        found.extend(directory.glob(pattern))
    return sorted([file for file in found if file.is_file()])


def guess_mime(path: Path, default: str) -> str:
    """Определяет MIME-тип файла.

    Args:
        path: Путь к файлу.
        default: MIME-тип по умолчанию.

    Returns:
        Определенный MIME-тип или значение по умолчанию.
    """
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or default


def is_landing_screenshot_fixture(path: Path) -> bool:
    """Проверяет, что изображение похоже на реальный скриншот лендинга.

    Args:
        path: Путь к PNG/JPG файлу.

    Returns:
        True для визуально насыщенных скриншотов, False для заглушек.
    """
    if path.stat().st_size < 50_000:
        return False
    with Image.open(path).convert("RGB") as image:
        colors = image.getcolors(maxcolors=2_000_000)
        unique_colors = len(colors) if colors is not None else 2_000_000
        stddev = sum(ImageStat.Stat(image).stddev) / 3
    return unique_colors >= 10_000 and stddev >= 20.0


def post_with_retry(
    url: str,
    *,
    context: str,
    attempts: int = 3,
    retry_for_statuses: tuple[int, ...] = (502, 503, 504),
    sleep_s: float = 1.0,
    **kwargs: object,
) -> requests.Response:
    """Выполняет POST-запрос с ретраями для нестабильных сценариев.

    Args:
        url: URL endpoint-а.
        context: Контекст запроса.
        attempts: Количество попыток.
        retry_for_statuses: Коды ответа для повторной попытки.
        sleep_s: Пауза между попытками.
        **kwargs: Параметры requests.post.

    Returns:
        Ответ последней успешной или финальной попытки.

    Raises:
        RuntimeError: Если запрос не удалось выполнить.
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
    """Выполняет multipart-запрос с повторным открытием файла на каждой попытке.

    Args:
        url: URL endpoint-а.
        context: Контекст сценария.
        field_name: Имя multipart-поля файла.
        file_path: Путь к файлу.
        mime: MIME-тип файла.
        data: Form-поля запроса.
        timeout: Таймаут запроса.
        attempts: Количество попыток.
        retry_for_statuses: Коды для ретрая.
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


def check_text_positive(summary: dict[str, int]) -> None:
    """Проверяет позитивные текстовые сценарии.

    Args:
        summary: Счетчик выполненных проверок.
    """
    files = iter_files(FULL / "texts" / "positive", ("*.txt",))
    if not files:
        raise RuntimeError("No positive text files in tests/data/fullscale/texts/positive")

    for file in files:
        response = post_with_retry(
            f"{BASE}/analyze/text",
            context=f"text positive {file.name}",
            json={"competitor_name": file.stem, "text": file.read_text(encoding="utf-8")},
            timeout=60,
        )
        assert_ok(response, f"text positive {file.name}")
        payload = response.json()
        assert_keys(
            payload,
            {"strengths", "weaknesses", "unique_offers", "recommendations", "summary"},
            f"text positive {file.name}",
        )
        summary["text_positive"] += 1


def check_text_negative(summary: dict[str, int]) -> None:
    """Проверяет негативные текстовые сценарии.

    Args:
        summary: Счетчик выполненных проверок.
    """
    short_file = FULL / "texts" / "negative" / "text_too_short.txt"
    if not short_file.exists():
        raise RuntimeError("Missing negative text fixture: text_too_short.txt")

    response = post_with_retry(
        f"{BASE}/analyze/text",
        context="text negative short",
        json={"competitor_name": "negative_short", "text": short_file.read_text(encoding="utf-8")},
        timeout=60,
    )
    assert_error(response, "text negative short")
    summary["text_negative"] += 1


def check_image_positive(summary: dict[str, int]) -> None:
    """Проверяет позитивные сценарии анализа изображений.

    Args:
        summary: Счетчик выполненных проверок.
    """
    images = iter_files(DATA / "images", ("*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp"))
    if not images:
        raise RuntimeError("No image files in tests/data/images")
    landing_images = [image for image in images if is_landing_screenshot_fixture(image)]
    if not landing_images:
        raise RuntimeError("No landing-like image fixtures for positive scenario")

    for image in landing_images:
        response = post_file_with_retry(
            f"{BASE}/analyze/image",
            context=f"image positive {image.name}",
            field_name="file",
            file_path=image,
            mime=guess_mime(image, "image/png"),
            data={"competitor_name": image.stem},
            timeout=60,
        )
        assert_ok(response, f"image positive {image.name}")
        payload = response.json()
        assert_keys(
            payload,
            {"description", "marketing_insights", "visual_style_score", "visual_style_analysis", "recommendations"},
            f"image positive {image.name}",
        )
        summary["image_positive"] += 1


def check_image_negative(summary: dict[str, int]) -> None:
    """Проверяет негативные сценарии анализа изображений.

    Args:
        summary: Счетчик выполненных проверок.
    """
    images = iter_files(DATA / "images", ("*.png", "*.jpg", "*.jpeg", "*.gif", "*.webp"))
    placeholder_images = [image for image in images if not is_landing_screenshot_fixture(image)]
    if not placeholder_images:
        raise RuntimeError("No placeholder-like image fixtures for negative landing scenario")

    for image in placeholder_images:
        response = post_file_with_retry(
            f"{BASE}/analyze/image",
            context=f"image negative semantic {image.name}",
            field_name="file",
            file_path=image,
            mime=guess_mime(image, "image/png"),
            data={"competitor_name": f"negative_semantic_{image.stem}"},
            timeout=60,
        )
        assert_ok(response, f"image negative semantic {image.name}")
        summary["image_negative"] += 1

    response = post_with_retry(
        f"{BASE}/analyze/image",
        context="image negative empty",
        data={"competitor_name": "negative_empty_image"},
        files={"file": ("empty.jpg", b"", "image/jpeg")},
        timeout=60,
    )
    assert_error(response, "image negative empty")
    summary["image_negative"] += 1


def check_pdf_positive(summary: dict[str, int]) -> None:
    """Проверяет позитивные сценарии анализа PDF.

    Args:
        summary: Счетчик выполненных проверок.
    """
    pdfs = iter_files(DATA / "pdfs", ("*.pdf",))
    if not pdfs:
        raise RuntimeError("No PDF files in tests/data/pdfs")

    for pdf in pdfs:
        response = post_file_with_retry(
            f"{BASE}/analyze/pdf",
            context=f"pdf positive {pdf.name}",
            field_name="file",
            file_path=pdf,
            mime="application/pdf",
            data={"competitor_name": pdf.stem},
            timeout=60,
        )
        assert_ok(response, f"pdf positive {pdf.name}")
        payload = response.json()
        assert_keys(
            payload,
            {"strengths", "weaknesses", "unique_offers", "recommendations", "summary"},
            f"pdf positive {pdf.name}",
        )
        summary["pdf_positive"] += 1


def check_pdf_negative(summary: dict[str, int]) -> None:
    """Проверяет негативные сценарии анализа PDF.

    Args:
        summary: Счетчик выполненных проверок.
    """
    invalids = iter_files(FULL / "pdfs" / "negative", ("*.pdf",))
    if not invalids:
        raise RuntimeError("No negative PDF files in tests/data/fullscale/pdfs/negative")

    for pdf in invalids:
        response = post_file_with_retry(
            f"{BASE}/analyze/pdf",
            context=f"pdf negative {pdf.name}",
            field_name="file",
            file_path=pdf,
            mime="application/pdf",
            data={"competitor_name": f"negative_{pdf.stem}"},
            timeout=60,
        )
        assert_error(response, f"pdf negative {pdf.name}")
        summary["pdf_negative"] += 1

    empty_response = post_with_retry(
        f"{BASE}/analyze/pdf",
        context="pdf negative empty",
        data={"competitor_name": "negative_empty_pdf"},
        files={"file": ("empty.pdf", b"", "application/pdf")},
        timeout=60,
    )
    assert_error(empty_response, "pdf negative empty")
    summary["pdf_negative"] += 1


def check_parse_positive(summary: dict[str, int]) -> None:
    """Проверяет позитивные сценарии парсинга URL.

    Args:
        summary: Счетчик выполненных проверок.
    """
    urls_path = FULL / "urls" / "positive_urls.txt"
    if not urls_path.exists():
        raise RuntimeError("Missing positive URLs file")
    urls = [line.strip() for line in urls_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not urls:
        raise RuntimeError("No positive URLs in positive_urls.txt")

    for url in urls:
        response = post_with_retry(
            f"{BASE}/parse/demo",
            context=f"parse positive {url}",
            json={"url": url},
            timeout=360,
        )
        assert_ok(response, f"parse positive {url}")
        payload = response.json()
        assert_keys(
            payload,
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
            f"parse positive {url}",
        )
        summary["parse_positive"] += 1


def check_parse_negative(summary: dict[str, int]) -> None:
    """Проверяет негативные сценарии парсинга URL.

    Args:
        summary: Счетчик выполненных проверок.
    """
    urls_path = FULL / "urls" / "negative_urls.txt"
    if not urls_path.exists():
        raise RuntimeError("Missing negative URLs file")
    urls = [line.strip() for line in urls_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not urls:
        raise RuntimeError("No negative URLs in negative_urls.txt")

    for url in urls:
        response = post_with_retry(
            f"{BASE}/parse/demo",
            context=f"parse negative {url}",
            json={"url": url},
            timeout=120,
        )
        if response.status_code >= 400:
            summary["parse_negative"] += 1
            continue
        payload = response.json()
        analyzed_chunks = payload.get("analyzed_chunks")
        summary_text = str(payload.get("summary", ""))
        fallback_ok = analyzed_chunks == 0 and "fallback" in summary_text.lower()
        if not fallback_ok:
            raise RuntimeError(
                f"parse negative {url} expected error/fallback, got "
                f"status={response.status_code} analyzed_chunks={analyzed_chunks}"
            )
        summary["parse_negative"] += 1


def check_history_cleanup(summary: dict[str, int]) -> None:
    """Проверяет очистку истории и runtime-файлов.

    Args:
        summary: Счетчик выполненных проверок.
    """
    data_root = ROOT / "data"
    uploads = data_root / "uploads"
    screenshots = data_root / "screenshots"
    uploads.mkdir(parents=True, exist_ok=True)
    screenshots.mkdir(parents=True, exist_ok=True)

    marker_upload = uploads / "fullscale_upload_marker.tmp"
    marker_screenshot = screenshots / "fullscale_screenshot_marker.tmp"
    marker_pdf = data_root / "tmp_uploaded.pdf"

    marker_upload.write_text("marker", encoding="utf-8")
    marker_screenshot.write_text("marker", encoding="utf-8")
    marker_pdf.write_text("marker", encoding="utf-8")

    response = requests.delete(f"{BASE}/history", timeout=30)
    assert_ok(response, "history delete")
    payload = response.json()
    if payload.get("status") != "cleared":
        raise RuntimeError("history delete did not return status=cleared")

    if marker_upload.exists() or marker_screenshot.exists() or marker_pdf.exists():
        raise RuntimeError("runtime files were not fully cleaned after DELETE /history")

    response_history = requests.get(f"{BASE}/history", timeout=30)
    assert_ok(response_history, "history get after clear")
    history_payload = response_history.json()
    if not isinstance(history_payload, list):
        raise RuntimeError("history payload should be list after clear")
    summary["history_cleanup"] += 1


def main() -> None:
    """Запускает полный набор полноформатных API-проверок."""
    global BASE
    BASE = resolve_base_url()
    summary: dict[str, int] = {
        "text_positive": 0,
        "text_negative": 0,
        "image_positive": 0,
        "image_negative": 0,
        "pdf_positive": 0,
        "pdf_negative": 0,
        "parse_positive": 0,
        "parse_negative": 0,
        "history_cleanup": 0,
    }

    check_text_positive(summary)
    check_text_negative(summary)
    check_image_positive(summary)
    check_image_negative(summary)
    check_pdf_positive(summary)
    check_pdf_negative(summary)
    check_parse_positive(summary)
    check_parse_negative(summary)
    check_history_cleanup(summary)

    print(json.dumps({"status": "ok", "suite": "fullscale", "checked": summary}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
