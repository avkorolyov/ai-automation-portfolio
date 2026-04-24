"""Проверки отказоустойчивости API при нестабильных внешних зависимостях."""

from __future__ import annotations

import json
import mimetypes
import os
import sys
from pathlib import Path

import requests


APP_HOST = os.getenv("APP_HOST", "127.0.0.1")
APP_PORT = os.getenv("APP_PORT", "8000")
ROOT = Path(__file__).resolve().parent.parent
TEST_DATA = ROOT / "tests" / "data"


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
    raise RuntimeError("Backend is not reachable on expected ports")


def require_ok_with_summary(response: requests.Response, context: str) -> None:
    """Проверяет корректный код и наличие summary-поля."""
    if response.status_code != 200:
        raise RuntimeError(f"{context}: expected 200, got {response.status_code}")
    payload = response.json()
    if "summary" not in payload:
        raise RuntimeError(f"{context}: summary field is missing")


def main() -> None:
    """Запускает сценарии resilience для fallback-веток."""
    base = resolve_base_url()
    summary = {
        "text_fallback_stability": 0,
        "image_fallback_stability": 0,
        "pdf_fallback_stability": 0,
        "parse_invalid_url_fallback": 0,
        "service_alive_after_failures": 0,
    }

    text_body = (TEST_DATA / "texts" / "eurookna.txt").read_text(encoding="utf-8")
    image_path = TEST_DATA / "images" / "melke_landing.png"
    image_mime, _ = mimetypes.guess_type(image_path.name)
    pdf_path = TEST_DATA / "pdfs" / "melke.pdf"

    # Повторяем сценарии, чтобы убедиться в устойчивости после fallback-веток.
    for index in range(3):
        response = requests.post(
            f"{base}/analyze/text",
            json={"competitor_name": f"resilience_text_{index}", "text": text_body},
            timeout=60,
        )
        require_ok_with_summary(response, f"text fallback run {index}")
        summary["text_fallback_stability"] += 1

    for index in range(3):
        with image_path.open("rb") as handler:
            response = requests.post(
                f"{base}/analyze/image",
                data={"competitor_name": f"resilience_image_{index}"},
                files={"file": (image_path.name, handler, image_mime or "image/png")},
                timeout=60,
            )
        if response.status_code != 200:
            raise RuntimeError(f"image fallback run {index}: expected 200, got {response.status_code}")
        payload = response.json()
        if "description" not in payload or "recommendations" not in payload:
            raise RuntimeError(f"image fallback run {index}: contract mismatch")
        summary["image_fallback_stability"] += 1

    for index in range(3):
        with pdf_path.open("rb") as handler:
            response = requests.post(
                f"{base}/analyze/pdf",
                data={"competitor_name": f"resilience_pdf_{index}"},
                files={"file": (pdf_path.name, handler, "application/pdf")},
                timeout=60,
            )
        require_ok_with_summary(response, f"pdf fallback run {index}")
        summary["pdf_fallback_stability"] += 1

    invalid_urls = ["not-a-url", "http://", "https://example.invalid"]
    for url in invalid_urls:
        response = requests.post(f"{base}/parse/demo", json={"url": url}, timeout=120)
        if response.status_code != 200:
            raise RuntimeError(f"parse invalid url {url}: expected 200 fallback, got {response.status_code}")
        payload = response.json()
        if payload.get("analyzed_chunks") != 0:
            raise RuntimeError(f"parse invalid url {url}: analyzed_chunks must be 0 in fallback")
        if "fallback" not in str(payload.get("summary", "")).lower():
            raise RuntimeError(f"parse invalid url {url}: fallback summary marker missing")
        summary["parse_invalid_url_fallback"] += 1

    # Проверяем, что сервис жив после серии деградационных сценариев.
    health_response = requests.get(f"{base}/health", timeout=10)
    if health_response.status_code != 200:
        raise RuntimeError("health check failed after resilience scenarios")
    if health_response.json().get("status") != "ok":
        raise RuntimeError("health payload mismatch after resilience scenarios")
    summary["service_alive_after_failures"] += 1

    print(json.dumps({"status": "ok", "suite": "resilience", "checked": summary}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
