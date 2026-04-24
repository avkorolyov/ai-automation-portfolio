"""Базовые security-проверки API и статических роутов."""

from __future__ import annotations

import json
import os
import sys

import requests


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
    raise RuntimeError("Backend is not reachable on expected ports")


def main() -> None:
    """Запускает security-smoke тесты без разрушительных действий."""
    base = resolve_base_url()
    summary = {
        "health_minimal_surface": 0,
        "path_traversal_protection": 0,
        "invalid_payload_no_traceback": 0,
        "not_found_no_traceback": 0,
        "cors_header_present": 0,
    }

    probe_headers = {"Origin": "https://security-check.local"}
    health_response = requests.get(f"{base}/health", headers=probe_headers, timeout=10)
    if health_response.status_code != 200:
        raise RuntimeError("health endpoint is unavailable")
    health_payload = health_response.json()
    if set(health_payload.keys()) != {"status"} or health_payload.get("status") != "ok":
        raise RuntimeError("health endpoint exposes unexpected fields")
    summary["health_minimal_surface"] += 1

    traversal_response = requests.get(f"{base}/frontend/../../.env", timeout=10)
    if traversal_response.status_code < 400:
        raise RuntimeError("path traversal probe unexpectedly succeeded")
    summary["path_traversal_protection"] += 1

    invalid_text_response = requests.post(
        f"{base}/analyze/text",
        json={"competitor_name": "security", "text": "short"},
        timeout=10,
    )
    if invalid_text_response.status_code != 422:
        raise RuntimeError(f"expected 422 for invalid payload, got {invalid_text_response.status_code}")
    invalid_body = invalid_text_response.text.lower()
    forbidden_markers = ("traceback", "file \"/", "line ")
    if any(marker in invalid_body for marker in forbidden_markers):
        raise RuntimeError("invalid payload response contains traceback internals")
    summary["invalid_payload_no_traceback"] += 1

    not_found_response = requests.get(f"{base}/definitely-not-existing-route", timeout=10)
    if not_found_response.status_code != 404:
        raise RuntimeError("unexpected status for unknown route probe")
    not_found_body = not_found_response.text.lower()
    if "traceback" in not_found_body:
        raise RuntimeError("404 response contains traceback internals")
    summary["not_found_no_traceback"] += 1

    cors_header = health_response.headers.get("access-control-allow-origin")
    if cors_header not in {"*", probe_headers["Origin"]}:
        raise RuntimeError("CORS header missing on health response")
    summary["cors_header_present"] += 1

    print(json.dumps({"status": "ok", "suite": "security", "checked": summary}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise
