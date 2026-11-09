import re
from pathlib import Path
from typing import Any

import httpx

from app.config import settings
from app.services.extractor import extract_document
from app.services.parser import parse_pages
from app.storage import save_result, update_metadata


def detect_languages(text: str) -> list[str]:
    languages = []

    if re.search(r"[A-Za-z]", text):
        languages.append("en")

    if re.search(r"[\u0900-\u097F]", text):
        languages.append("hi")

    return languages or ["unknown"]


def attach_media(
    sections: list[dict[str, Any]],
    media: list[dict[str, Any]],
) -> None:
    media_by_page: dict[int, list[dict[str, Any]]] = {}

    for item in media:
        page = item.get("source_page")
        if page is not None:
            media_by_page.setdefault(page, []).append(item)

    for section in sections:
        for question in section["questions"]:
            page = question.get("source", {}).get("page")
            if page is None:
                continue

            question["media"] = [
                item.copy()
                for item in media_by_page.get(page, [])
            ]


async def ollama_available() -> bool:
    if not settings.ollama_enabled:
        return False

    try:
        async with httpx.AsyncClient(
            timeout=3.0,
        ) as client:
            response = await client.get(
                f"{settings.ollama_base_url.rstrip('/')}/api/tags"
            )
            response.raise_for_status()
            data = response.json()

        models = [
            item.get("name", "")
            for item in data.get("models", [])
        ]

        return any(
            model == settings.ollama_model
            or model.startswith(f"{settings.ollama_model}:")
            for model in models
        )
    except Exception:
        return False


async def run_ollama_check() -> dict[str, Any]:
    available = await ollama_available()

    return {
        "enabled": settings.ollama_enabled,
        "available": available,
        "model": settings.ollama_model if settings.ollama_enabled else None,
    }


def convert_document(
    conversion_id: str,
    source_path: Path,
    media_dir: Path,
) -> dict[str, Any]:
    update_metadata(
        conversion_id,
        status="processing",
        progress=5,
        stage="Extracting document content",
    )

    extracted = extract_document(source_path, media_dir)

    pages = extracted["pages"]
    combined_text = "\n".join(
        page["text"] for page in pages
    )

    update_metadata(
        conversion_id,
        progress=45,
        stage="Identifying questions and sections",
    )

    sections = parse_pages(pages)

    update_metadata(
        conversion_id,
        progress=75,
        stage="Associating extracted media",
    )

    attach_media(sections, extracted["media"])

    total_questions = sum(
        len(section["questions"])
        for section in sections
    )

    result = {
        "document": {
            "title": extracted["title"],
            "total_questions": total_questions,
            "total_pages": extracted["page_count"],
            "source_filename": source_path.name,
            "source_format": source_path.suffix.lower().lstrip("."),
            "language": detect_languages(combined_text),
        },
        "sections": sections,
    }

    update_metadata(
        conversion_id,
        progress=90,
        stage="Saving structured JSON",
    )

    save_result(conversion_id, result)

    update_metadata(
        conversion_id,
        status="completed",
        progress=100,
        stage="Conversion complete",
        error=None,
        result=result,
    )

    return result


def fail_conversion(conversion_id: str, error: str) -> None:
    update_metadata(
        conversion_id,
        status="failed",
        progress=100,
        stage="Conversion failed",
        error=error,
        result=None,
    )