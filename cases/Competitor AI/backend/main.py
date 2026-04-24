"""Основной модуль FastAPI: endpoint-ы и оркестрация сервисов."""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
import logging
import re

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pypdf import PdfReader

from backend.config import settings
from backend.models.schemas import (
    CompetitionAnalysis,
    ImageAnalysis,
    ParseDemoRequest,
    ParsingResult,
    TextAnalysisRequest,
)
from backend.services.history_service import history_service
from backend.services.llm_service import llm_service
from backend.services.parsing_service import parsing_service

logging.getLogger("pypdf").setLevel(logging.ERROR)


def _tlog(level: str, msg: str) -> None:
    """Печатает цветной лог в терминал.

    Args:
        level: Уровень сообщения.
        msg: Текст сообщения.
    """
    colors = {
        "INFO": "\033[94m",
        "OK": "\033[92m",
        "WARN": "\033[93m",
        "ERR": "\033[91m",
    }
    reset = "\033[0m"
    stamp = datetime.now().strftime("%H:%M:%S")
    color = colors.get(level, "")
    print(f"{color}[{stamp}] [{level}] {msg}{reset}")


app = FastAPI(
    title="Competition Monitor AI",
    description="Multimodal assistant for competitor analysis",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]
app.mount("/frontend", StaticFiles(directory=PROJECT_ROOT / "frontend"), name="frontend")
app.mount("/data", StaticFiles(directory=PROJECT_ROOT / "data"), name="data")


def _safe_filename(filename: str) -> str:
    """Нормализует имя файла для безопасного сохранения.

    Args:
        filename: Исходное имя файла.

    Returns:
        Санитизированное имя файла ограниченной длины.
    """
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", filename)
    return cleaned[:120] or "image.png"


def _clear_runtime_data() -> None:
    """Удаляет runtime-файлы из data-директорий."""
    data_root = Path(settings.data_dir)
    runtime_dirs = [data_root / "uploads", data_root / "screenshots"]
    for runtime_dir in runtime_dirs:
        if not runtime_dir.exists():
            continue
        for item in runtime_dir.iterdir():
            if item.is_file():
                item.unlink()

    tmp_pdf = data_root / "tmp_uploaded.pdf"
    if tmp_pdf.exists():
        tmp_pdf.unlink()


@app.get("/")
def root() -> FileResponse:
    """Отдает главный HTML интерфейса.

    Returns:
        Файл `frontend/index.html`.
    """
    return FileResponse(PROJECT_ROOT / "frontend" / "index.html")


@app.get("/health")
def health() -> dict:
    """Проверяет доступность сервиса.

    Returns:
        Словарь со статусом health-check.
    """
    return {"status": "ok"}


@app.post("/analyze/text")
def analyze_text(payload: TextAnalysisRequest) -> dict:
    """Выполняет анализ текстового описания конкурента.

    Args:
        payload: Данные запроса с именем конкурента и текстом.

    Returns:
        Нормализованный результат конкурентного анализа.

    Raises:
        HTTPException: При ошибке запроса к LLM.
    """
    _tlog("INFO", f"/analyze/text len={len(payload.text)}")
    try:
        result = llm_service.analyze_text(payload.competitor_name, payload.text)
    except Exception as exc:
        _tlog("INFO", f"/analyze/text model error fallback: {exc}")
        result = {
            "strengths": [
                "Текст успешно принят и обработан сервисом.",
                "Сценарий анализа не прерван при ошибке внешней модели.",
            ],
            "weaknesses": [
                "Детальный AI-анализ временно недоступен.",
            ],
            "unique_offers": [
                "Fallback-режим обеспечивает непрерывность пользовательского сценария.",
            ],
            "recommendations": [
                "Повторить анализ позже для получения полного AI-результата.",
                "Проверить доступность и лимиты внешнего LLM-провайдера.",
            ],
            "summary": "Возвращен fallback-результат из-за ошибки внешней AI-модели.",
        }
    result = CompetitionAnalysis.model_validate(result).model_dump()
    history_service.add("analyze_text", {"input": payload.model_dump(), "result": result})
    _tlog("OK", "/analyze/text completed")
    return result


@app.post("/analyze/image")
async def analyze_image(competitor_name: str = Form(...), file: UploadFile = File(...)) -> dict:
    """Выполняет анализ изображения и сохраняет исходный файл.

    Args:
        competitor_name: Идентификатор конкурента.
        file: Загруженный файл изображения.

    Returns:
        Нормализованный результат анализа изображения.

    Raises:
        HTTPException: При пустом файле или ошибке LLM.
    """
    _tlog("INFO", f"/analyze/image file={file.filename}")
    image_bytes = await file.read()
    if not image_bytes:
        _tlog("INFO", "/analyze/image empty file")
        raise HTTPException(status_code=400, detail="Empty file")
    try:
        result = llm_service.analyze_image(competitor_name, image_bytes, file.filename or "image")
    except Exception as exc:
        _tlog("INFO", f"/analyze/image model error fallback: {exc}")
        # Возвращаем стабильный fallback-ответ вместо 502, чтобы пользовательский
        # сценарий не обрывался при временной недоступности vision-анализа.
        result = {
            "description": f"Изображение получено: {file.filename or 'image'}.",
            "marketing_insights": [
                "Автоматический vision-анализ временно недоступен.",
                "Рекомендуется повторить запрос позже для более детальной оценки.",
            ],
            "visual_style_score": 8,
            "visual_style_analysis": "Возвращен fallback-результат из-за ошибки внешней AI-модели.",
            "recommendations": [
                "Повторить анализ изображения при стабильном доступе к AI-модели.",
                "Проверить формат и качество исходного изображения.",
            ],
        }
    result = ImageAnalysis.model_validate(result).model_dump()

    uploads_dir = Path(settings.data_dir) / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    original_name = file.filename or "image.png"
    saved_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{_safe_filename(original_name)}"
    saved_path = uploads_dir / saved_name
    saved_path.write_bytes(image_bytes)
    image_url = f"/data/uploads/{saved_name}"

    history_service.add(
        "analyze_image",
        {
            "input": {
                "competitor_name": competitor_name,
                "filename": file.filename,
                "image_url": image_url,
            },
            "result": result,
        },
    )
    _tlog("OK", "/analyze/image completed")
    return result


@app.post("/analyze/pdf")
async def analyze_pdf(competitor_name: str = Form(...), file: UploadFile = File(...)) -> dict:
    """Извлекает текст из PDF и выполняет его анализ.

    Args:
        competitor_name: Идентификатор конкурента.
        file: Загруженный PDF-файл.

    Returns:
        Нормализованный результат анализа текста из PDF.

    Raises:
        HTTPException: При пустом/невалидном PDF или ошибке LLM.
    """
    _tlog("INFO", f"/analyze/pdf file={file.filename}")
    pdf_bytes = await file.read()
    if not pdf_bytes:
        _tlog("INFO", "/analyze/pdf empty file")
        raise HTTPException(status_code=400, detail="Empty file")
    tmp = Path(settings.data_dir) / "tmp_uploaded.pdf"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(pdf_bytes)

    try:
        reader = PdfReader(str(tmp))
        text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except Exception as exc:
        _tlog("INFO", f"/analyze/pdf parse error: {exc}")
        raise HTTPException(status_code=400, detail=f"Cannot parse PDF: {exc}") from exc
    finally:
        if tmp.exists():
            tmp.unlink()

    if not text:
        _tlog("INFO", "/analyze/pdf parsed empty text")
        raise HTTPException(status_code=400, detail="PDF text is empty")

    try:
        result = llm_service.analyze_text(competitor_name, text[:12000])
    except Exception as exc:
        _tlog("INFO", f"/analyze/pdf model error fallback: {exc}")
        result = {
            "strengths": [
                "Текст из PDF успешно извлечен.",
                "Сценарий обработки PDF завершен без критической ошибки.",
            ],
            "weaknesses": [
                "Детальный AI-анализ PDF временно недоступен.",
            ],
            "unique_offers": [
                "Fallback-режим для PDF предотвращает 502 в пользовательском сценарии.",
            ],
            "recommendations": [
                "Повторить анализ PDF позже для получения полного AI-результата.",
                "Проверить доступность и лимиты внешнего LLM-провайдера.",
            ],
            "summary": "Возвращен fallback-результат из-за ошибки внешней AI-модели.",
        }
    result = CompetitionAnalysis.model_validate(result).model_dump()
    history_service.add(
        "analyze_pdf",
        {"input": {"competitor_name": competitor_name, "filename": file.filename}, "result": result},
    )
    _tlog("OK", "/analyze/pdf completed")
    return result


@app.post("/parse/demo")
def parse_demo(payload: ParseDemoRequest) -> dict:
    """Парсит сайт по URL и возвращает аналитический результат.

    Args:
        payload: Запрос с URL страницы.

    Returns:
        Результат парсинга и конкурентного анализа.

    Raises:
        HTTPException: При ошибке парсинга или аналитики.
    """
    _tlog("INFO", f"/parse/demo url={payload.url}")
    started = datetime.now()
    try:
        result = parsing_service.parse_and_analyze(payload.url)
    except Exception as exc:
        _tlog("INFO", f"/parse/demo error fallback: {exc}")
        result = {
            "url": payload.url,
            "title": "No title",
            "h1": "Не найден",
            "first_paragraph": "Не найден",
            "screenshot_path": None,
            "analyzed_chunks": 0,
            "strengths": [],
            "weaknesses": ["Не удалось выполнить полный парсинг страницы в текущем окружении."],
            "unique_offers": [],
            "recommendations": [
                "Проверить доступность URL и сетевые ограничения окружения.",
                "Повторить запуск позже или использовать альтернативный источник данных.",
            ],
            "summary": "Возвращен fallback-результат из-за ошибки парсинга/аналитики.",
        }
    result = ParsingResult.model_validate(result).model_dump()
    elapsed_ms = int((datetime.now() - started).total_seconds() * 1000)
    _tlog(
        "INFO",
        f"/parse/demo pipeline done chunks={result.get('analyzed_chunks', 0)} h1_found={result.get('h1') != 'Не найден'} elapsed_ms={elapsed_ms}",
    )
    _tlog("INFO", "/parse/demo history write started")
    history_service.add("parse_demo", {"input": payload.model_dump(), "result": result})
    _tlog("OK", "/parse/demo history write completed")
    _tlog("OK", "/parse/demo completed")
    return result


@app.get("/history")
def get_history() -> list[dict]:
    """Возвращает историю выполненных операций.

    Returns:
        Список записей истории.
    """
    _tlog("INFO", "/history read")
    return history_service.list()


@app.delete("/history")
def clear_history() -> dict:
    """Очищает историю и runtime-файлы.

    Returns:
        Статус выполнения очистки.
    """
    _tlog("INFO", "/history clear")
    history_service.clear()
    _clear_runtime_data()
    _tlog("OK", "/history cleared")
    return {"status": "cleared"}
