"""Pydantic-схемы запросов и ответов backend API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class TextAnalysisRequest(BaseModel):
    """Запрос на анализ текста конкурента."""

    competitor_name: str = Field(..., min_length=2)
    text: str = Field(..., min_length=20)


class ParseDemoRequest(BaseModel):
    """Запрос на парсинг и анализ сайта по URL."""

    url: str


class CompetitionAnalysis(BaseModel):
    """Структура результата текстового/PDF анализа."""

    strengths: list[str]
    weaknesses: list[str]
    unique_offers: list[str]
    recommendations: list[str]
    summary: str


class ImageAnalysis(BaseModel):
    """Структура результата анализа изображения."""

    description: str
    marketing_insights: list[str]
    visual_style_score: float = Field(..., ge=0, le=16)
    visual_style_analysis: str
    recommendations: list[str]


class ParsingResult(BaseModel):
    """Структура результата парсинга сайта и последующей аналитики."""

    url: str
    title: str
    h1: str
    first_paragraph: str
    screenshot_path: str | None = None
    analyzed_chunks: int
    strengths: list[str]
    weaknesses: list[str]
    unique_offers: list[str]
    recommendations: list[str]
    summary: str


class DialogueHistoryItem(BaseModel):
    """Запись в истории выполненных операций."""

    source: str
    payload: dict
    created_at: str
