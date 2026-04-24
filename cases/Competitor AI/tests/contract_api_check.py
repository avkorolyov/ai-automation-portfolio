"""Контрактные API-тесты для ключевых endpoint-ов."""

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


def assert_required(payload: dict, required: set[str], context: str) -> None:
    """Проверяет наличие обязательных ключей в словаре."""
    missing = sorted(required - set(payload))
    if missing:
        raise RuntimeError(f"{context}: missing keys {missing}")


def assert_types(payload: dict, mapping: dict[str, type | tuple[type, ...]], context: str) -> None:
    """Проверяет типы полей контракта."""
    for key, expected_type in mapping.items():
        if key not in payload:
            raise RuntimeError(f"{context}: missing key '{key}'")
        expected_tuple = expected_type if isinstance(expected_type, tuple) else (expected_type,)
        if not isinstance(payload[key], expected_tuple):
            expected_names = "/".join(item.__name__ for item in expected_tuple)
            raise RuntimeError(
                f"{context}: key '{key}' has type {type(payload[key]).__name__}, expected {expected_names}"
            )


def main() -> None:
    """Запускает контрактные проверки API."""
    base = resolve_base_url()
    summary = {"text": 0, "image": 0, "pdf": 0, "parse": 0, "history": 0, "errors": 0}

    # /analyze/text contract
    text_file = TEST_DATA / "texts" / "melke.txt"
    text_response = requests.post(
        f"{base}/analyze/text",
        json={"competitor_name": "contract_text", "text": text_file.read_text(encoding="utf-8")},
        timeout=60,
    )
    if text_response.status_code != 200:
        raise RuntimeError(f"text contract failed: {text_response.status_code}")
    text_payload = text_response.json()
    assert_required(text_payload, {"strengths", "weaknesses", "unique_offers", "recommendations", "summary"}, "text")
    assert_types(
        text_payload,
        {
            "strengths": list,
            "weaknesses": list,
            "unique_offers": list,
            "recommendations": list,
            "summary": str,
        },
        "text",
    )
    summary["text"] += 1

    # /analyze/image contract
    image_path = TEST_DATA / "images" / "eurookna_landing.png"
    image_mime, _ = mimetypes.guess_type(image_path.name)
    with image_path.open("rb") as handler:
        image_response = requests.post(
            f"{base}/analyze/image",
            data={"competitor_name": "contract_image"},
            files={"file": (image_path.name, handler, image_mime or "image/png")},
            timeout=60,
        )
    if image_response.status_code != 200:
        raise RuntimeError(f"image contract failed: {image_response.status_code}")
    image_payload = image_response.json()
    assert_required(
        image_payload,
        {"description", "marketing_insights", "visual_style_score", "visual_style_analysis", "recommendations"},
        "image",
    )
    assert_types(
        image_payload,
        {
            "description": str,
            "marketing_insights": list,
            "visual_style_score": (int, float),
            "visual_style_analysis": str,
            "recommendations": list,
        },
        "image",
    )
    summary["image"] += 1

    # /analyze/pdf contract
    pdf_path = TEST_DATA / "pdfs" / "melke.pdf"
    with pdf_path.open("rb") as handler:
        pdf_response = requests.post(
            f"{base}/analyze/pdf",
            data={"competitor_name": "contract_pdf"},
            files={"file": (pdf_path.name, handler, "application/pdf")},
            timeout=60,
        )
    if pdf_response.status_code != 200:
        raise RuntimeError(f"pdf contract failed: {pdf_response.status_code}")
    pdf_payload = pdf_response.json()
    assert_required(pdf_payload, {"strengths", "weaknesses", "unique_offers", "recommendations", "summary"}, "pdf")
    assert_types(
        pdf_payload,
        {
            "strengths": list,
            "weaknesses": list,
            "unique_offers": list,
            "recommendations": list,
            "summary": str,
        },
        "pdf",
    )
    summary["pdf"] += 1

    # /parse/demo contract
    parse_response = requests.post(f"{base}/parse/demo", json={"url": "https://example.com"}, timeout=120)
    if parse_response.status_code != 200:
        raise RuntimeError(f"parse contract failed: {parse_response.status_code}")
    parse_payload = parse_response.json()
    assert_required(
        parse_payload,
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
        "parse",
    )
    assert_types(
        parse_payload,
        {
            "url": str,
            "title": str,
            "h1": str,
            "first_paragraph": str,
            "analyzed_chunks": int,
            "strengths": list,
            "weaknesses": list,
            "unique_offers": list,
            "recommendations": list,
            "summary": str,
        },
        "parse",
    )
    summary["parse"] += 1

    # /history contract
    history_response = requests.get(f"{base}/history", timeout=30)
    if history_response.status_code != 200:
        raise RuntimeError(f"history contract failed: {history_response.status_code}")
    history_payload = history_response.json()
    if not isinstance(history_payload, list):
        raise RuntimeError("history payload should be list")
    summary["history"] += 1

    # Error contract for validation
    error_response = requests.post(
        f"{base}/analyze/text",
        json={"competitor_name": "contract_error", "text": "short"},
        timeout=30,
    )
    if error_response.status_code != 422:
        raise RuntimeError(f"expected 422 for invalid text, got {error_response.status_code}")
    error_payload = error_response.json()
    if "detail" not in error_payload:
        raise RuntimeError("error contract: 'detail' key missing")
    summary["errors"] += 1

    print(json.dumps({"status": "ok", "suite": "contract_api", "checked": summary}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
