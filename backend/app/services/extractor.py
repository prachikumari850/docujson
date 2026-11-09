import re
from pathlib import Path
from typing import Any

import fitz
from docx import Document
from PIL import Image
from io import BytesIO


def safe_filename(value: str) -> str:
    value = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE)
    return value.strip("._") or "media"


def image_extension(data: bytes, fallback: str = "png") -> str:
    try:
        with Image.open(BytesIO(data)) as image:
            return (image.format or fallback).lower().replace("jpeg", "jpg")
    except Exception:
        return fallback


def save_media(
    data: bytes,
    media_dir: Path,
    stem: str,
    media_type: str,
    page: int | None = None,
) -> dict[str, Any] | None:
    if not data:
        return None

    extension = image_extension(data)
    filename = safe_filename(f"{stem}.{extension}")
    destination = media_dir / filename

    counter = 1
    while destination.exists():
        filename = safe_filename(f"{stem}_{counter}.{extension}")
        destination = media_dir / filename
        counter += 1

    destination.write_bytes(data)

    return {
        "asset_id": destination.stem,
        "filename": filename,
        "type": media_type,
        "source_page": page,
    }


def extract_pdf(path: Path, media_dir: Path) -> dict[str, Any]:
    document = fitz.open(path)
    pages: list[dict[str, Any]] = []
    media: list[dict[str, Any]] = []

    try:
        for page_index, page in enumerate(document):
            page_number = page_index + 1
            text = page.get_text("text", sort=True).strip()

            pages.append(
                {
                    "page": page_number,
                    "text": text,
                }
            )

            image_count = 0
            for image_info in page.get_images(full=True):
                xref = image_info[0]
                extracted = document.extract_image(xref)
                saved = save_media(
                    extracted.get("image", b""),
                    media_dir,
                    f"page_{page_number}_image_{image_count + 1}",
                    "image",
                    page_number,
                )
                if saved:
                    media.append(saved)
                    image_count += 1

            drawings = page.get_drawings()
            if drawings:
                pixmap = page.get_pixmap(
                    matrix=fitz.Matrix(1.5, 1.5),
                    alpha=False,
                )
                saved = save_media(
                    pixmap.tobytes("png"),
                    media_dir,
                    f"page_{page_number}_vector_preview",
                    "diagram",
                    page_number,
                )
                if saved:
                    media.append(saved)

        metadata = document.metadata or {}
        return {
            "pages": pages,
            "media": media,
            "page_count": len(document),
            "title": metadata.get("title") or path.stem,
        }
    finally:
        document.close()


def extract_docx(path: Path, media_dir: Path) -> dict[str, Any]:
    document = Document(path)

    paragraphs = [
        paragraph.text.strip()
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    ]

    pages = [
        {
            "page": 1,
            "text": "\n".join(paragraphs),
        }
    ]

    media: list[dict[str, Any]] = []

    for index, relationship in enumerate(document.part.rels.values(), start=1):
        if "image" not in relationship.reltype:
            continue

        try:
            data = relationship.target_part.blob
        except Exception:
            continue

        saved = save_media(
            data,
            media_dir,
            f"document_image_{index}",
            "image",
            1,
        )
        if saved:
            media.append(saved)

    for table in document.tables:
        rows = []
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            rows.append(" | ".join(cells))
        if rows:
            pages[0]["text"] += "\n" + "\n".join(rows)

    properties = document.core_properties

    return {
        "pages": pages,
        "media": media,
        "page_count": None,
        "title": properties.title or path.stem,
    }


def extract_txt(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()

    text = None
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    if text is None:
        text = raw.decode("utf-8", errors="replace")

    return {
        "pages": [{"page": 1, "text": text.strip()}],
        "media": [],
        "page_count": None,
        "title": path.stem,
    }


def extract_document(path: Path, media_dir: Path) -> dict[str, Any]:
    extension = path.suffix.lower()

    if extension == ".pdf":
        return extract_pdf(path, media_dir)

    if extension == ".docx":
        return extract_docx(path, media_dir)

    if extension == ".txt":
        return extract_txt(path)

    raise ValueError("Unsupported file type. Upload a PDF, DOCX or TXT file.")