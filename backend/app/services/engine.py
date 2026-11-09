import json
import logging
import re
from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image
from docx import Document

from app.storage import update_job

logger = logging.getLogger("docujson")


QUESTION_RE = re.compile(
    r"^\s*(?:Q(?:uestion)?\.?\s*)?(\d{1,3})\s*[).:]\s*(.*)$",
    re.IGNORECASE,
)

OPTION_RE = re.compile(
    r"^\s*[\(\[]?([A-Da-d])[\)\].:]?\s*(.+?)\s*$"
)

ANSWER_RE = re.compile(
    r"^\s*(?:ans(?:wer)?|उत्तर)\s*[:.-]\s*(.+)$",
    re.IGNORECASE,
)

SECTION_RE = re.compile(
    r"^\s*SECTION\s*[-:]?\s*([A-Z])(?:\s*\(.*\))?\s*$",
    re.IGNORECASE,
)


def bilingual(text: str) -> dict:
    text = text.strip()

    if not text:
        return {"en": None, "hi": None}

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    english = []
    hindi = []

    for line in lines:
        has_hindi = bool(
            re.search(r"[\u0900-\u097F]", line)
        )
        has_english = bool(
            re.search(r"[A-Za-z]", line)
        )

        if has_hindi and has_english:
            english.append(line)
            hindi.append(line)
        elif has_hindi:
            hindi.append(line)
        elif has_english:
            english.append(line)

    if english or hindi:
        return {
            "en": "\n".join(english) or None,
            "hi": "\n".join(hindi) or None,
        }

    return {
        "en": text,
        "hi": None,
    }


def clean_marks(text: str):
    pattern = re.compile(
        r"\[\s*(\d+(?:\.\d+)?)\s*(?:marks?)?\s*\]"
        r"|\(\s*(\d+(?:\.\d+)?)\s*marks?\s*\)",
        re.IGNORECASE,
    )

    match = pattern.search(text)

    if not match:
        return text.strip(), None

    value = next(
        group for group in match.groups()
        if group is not None
    )

    cleaned = (
        text[:match.start()] + text[match.end():]
    ).strip()

    return cleaned, float(value)


def image_bytes(data: bytes):
    try:
        image = Image.open(BytesIO(data))
        image.load()
        return image
    except Exception:
        return None


def save_asset(
    data: bytes,
    media_dir: Path,
    name: str,
    media_type: str,
    page_number: int,
    bbox=None,
):
    image = image_bytes(data)

    if image is None:
        return None

    width, height = image.size

    if width < 70 or height < 45:
        return None

    if width * height < 9000:
        return None

    ratio = width / max(height, 1)

    if ratio > 12 or ratio < 1 / 12:
        return None

    extension = (
        image.format or "PNG"
    ).lower()

    if extension == "jpeg":
        extension = "jpg"

    if extension not in {
        "png", "jpg", "webp", "bmp", "tiff"
    }:
        extension = "png"

    filename = f"{name}.{extension}"
    destination = media_dir / filename

    if destination.exists():
        return None

    destination.write_bytes(data)

    return {
        "asset_id": Path(filename).stem,
        "filename": filename,
        "type": media_type,
        "source_page": page_number,
        "bbox": list(bbox) if bbox else None,
        "content": None,
    }


def extract_pdf(path: Path, media_dir: Path):
    document = fitz.open(path)

    pages = []
    media = []

    try:
        for page_index, page in enumerate(document):
            page_number = page_index + 1

            blocks = page.get_text(
                "dict",
                sort=True,
            ).get("blocks", [])

            text_lines = []

            for block in blocks:
                if block.get("type") != 0:
                    continue

                for line in block.get("lines", []):
                    spans = line.get("spans", [])

                    text = "".join(
                        span.get("text", "")
                        for span in spans
                    ).strip()

                    if not text:
                        continue

                    bbox = fitz.Rect(line["bbox"])

                    text_lines.append(
                        (
                            bbox.y0,
                            bbox.x0,
                            text,
                            bbox,
                        )
                    )

            text_lines.sort(
                key=lambda item: (item[0], item[1])
            )

            page_text = "\n".join(
                item[2] for item in text_lines
            )

            legacy_count = len(
                re.findall(
                    r"[\uF000-\uF8FF"
                    r"\uF0A0-\uF0FF]",
                    page_text,
                )
            )

            needs_ocr = (
                legacy_count > max(
                    8,
                    int(len(page_text) * 0.08),
                )
                or len(page_text) < 30
            )

            pages.append(
                {
                    "page": page_number,
                    "text": page_text,
                    "lines": text_lines,
                    "needs_ocr": needs_ocr,
                }
            )

            image_index = 0

            for block in blocks:
                if block.get("type") != 1:
                    continue

                rect = fitz.Rect(
                    block.get("bbox", (0, 0, 0, 0))
                )

                if rect.width < 48 or rect.height < 35:
                    continue

                if rect.y0 < page.rect.height * 0.09:
                    continue

                if rect.y1 > page.rect.height * 0.94:
                    continue

                if (
                    rect.width * rect.height
                    < page.rect.width
                    * page.rect.height
                    * 0.002
                ):
                    continue

                data = block.get("image")

                if not data:
                    continue

                image_index += 1

                asset = save_asset(
                    data,
                    media_dir,
                    f"p{page_number}_img{image_index}",
                    "image",
                    page_number,
                    rect,
                )

                if asset:
                    media.append(asset)

            drawing_regions = []

            for drawing in page.get_drawings():
                rect = fitz.Rect(drawing["rect"])

                if rect.width < 45 or rect.height < 35:
                    continue

                if rect.y0 < page.rect.height * 0.10:
                    continue

                if rect.y1 > page.rect.height * 0.94:
                    continue

                if (
                    rect.width * rect.height
                    < page.rect.width
                    * page.rect.height
                    * 0.0015
                ):
                    continue

                duplicate = any(
                    rect.intersects(existing)
                    and (
                        rect | existing
                    ).get_area()
                    < (
                        rect.get_area()
                        + existing.get_area()
                    ) * 1.35
                    for existing in drawing_regions
                )

                if not duplicate:
                    drawing_regions.append(rect)

            for index, rect in enumerate(
                drawing_regions,
                start=1,
            ):
                clip = (
                    rect + (-5, -5, 5, 5)
                ) & page.rect

                pixmap = page.get_pixmap(
                    matrix=fitz.Matrix(2, 2),
                    clip=clip,
                    alpha=False,
                )

                asset = save_asset(
                    pixmap.tobytes("png"),
                    media_dir,
                    f"p{page_number}_diagram{index}",
                    "diagram",
                    page_number,
                    clip,
                )

                if asset:
                    media.append(asset)

        return {
            "pages": pages,
            "media": media,
            "page_count": len(document),
            "title": (
                (document.metadata or {}).get("title")
                or path.stem
            ),
        }

    finally:
        document.close()


def extract_docx(path: Path, media_dir: Path):
    document = Document(path)

    text_parts = []

    for paragraph in document.paragraphs:
        if paragraph.text.strip():
            text_parts.append(paragraph.text.strip())

    for table in document.tables:
        for row in table.rows:
            text_parts.append(
                " | ".join(
                    cell.text.strip()
                    for cell in row.cells
                )
            )

    media = []

    for index, relationship in enumerate(
        document.part.rels.values(),
        start=1,
    ):
        if "image" not in relationship.reltype:
            continue

        asset = save_asset(
            relationship.target_part.blob,
            media_dir,
            f"docx_img{index}",
            "image",
            1,
        )

        if asset:
            media.append(asset)

    return {
        "pages": [
            {
                "page": 1,
                "text": "\n".join(text_parts),
                "lines": [],
                "needs_ocr": False,
            }
        ],
        "media": media,
        "page_count": None,
        "title": (
            document.core_properties.title
            or path.stem
        ),
    }


def extract_txt(path: Path):
    raw = path.read_bytes()

    text = None

    for encoding in (
        "utf-8-sig",
        "utf-8",
        "utf-16",
        "cp1252",
    ):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    if text is None:
        text = raw.decode(
            "utf-8",
            errors="replace",
        )

    return {
        "pages": [
            {
                "page": 1,
                "text": text,
                "lines": [],
                "needs_ocr": False,
            }
        ],
        "media": [],
        "page_count": None,
        "title": path.stem,
    }


def extract(path: Path, media_dir: Path):
    extension = path.suffix.lower()

    if extension == ".pdf":
        return extract_pdf(path, media_dir)

    if extension == ".docx":
        return extract_docx(path, media_dir)

    if extension == ".txt":
        return extract_txt(path)

    raise ValueError(
        f"Unsupported file format: {path.name}"
    )


def parse_questions(pages: list[dict]):
    sections = []

    current_section = {
        "section_name": "General",
        "questions": [],
    }

    question = None
    question_counter = 0

    def flush_question():
        nonlocal question

        if question is None:
            return

        raw_text = "\n".join(
            question.pop("_lines")
        ).strip()

        if (
            not raw_text
            and not question["options"]
            and not question["correct_answer"]
        ):
            question = None
            return

        raw_text, marks = clean_marks(raw_text)

        question["question"] = bilingual(raw_text)

        question["marks"] = marks

        question["question_type"] = (
            "mcq"
            if len(question["options"]) >= 2
            else "subjective"
        )

        question["review_required"] = (
            not bool(raw_text)
        )

        current_section["questions"].append(
            question
        )

        question = None

    def flush_section():
        flush_question()

        if current_section["questions"]:
            sections.append(current_section.copy())

    for page in pages:
        page_number = page["page"]

        for line in page["text"].splitlines():
            text = line.strip()

            if not text:
                continue

            section_match = SECTION_RE.match(text)

            if section_match:
                flush_section()

                current_section = {
                    "section_name": (
                        f"Section {section_match.group(1)}"
                    ),
                    "questions": [],
                }

                continue

            question_match = QUESTION_RE.match(text)

            if question_match:
                number = int(question_match.group(1))

                if page_number <= 2:
                    continue

                flush_question()

                question_counter += 1

                initial_text = (
                    question_match.group(2).strip()
                )

                question = {
                    "question_id": f"q{question_counter}",
                    "question_number": number,
                    "question_type": "subjective",
                    "question": {
                        "en": None,
                        "hi": None,
                    },
                    "options": [],
                    "correct_answer": None,
                    "marks": None,
                    "source": {
                        "page": page_number,
                    },
                    "media": [],
                    "review_required": False,
                    "_lines": (
                        [initial_text]
                        if initial_text
                        else []
                    ),
                }

                continue

            if question is None:
                continue

            option_match = OPTION_RE.match(text)

            if option_match:
                question["options"].append(
                    {
                        "id": option_match.group(1).upper(),
                        "text": option_match.group(2).strip(),
                    }
                )
                continue

            answer_match = ANSWER_RE.match(text)

            if answer_match:
                question["correct_answer"] = (
                    answer_match.group(1).strip()
                )
                continue

            question["_lines"].append(text)

    flush_question()

    if current_section["questions"]:
        sections.append(current_section)

    for section in sections:
        merged = []
        by_number = {}

        for item in section["questions"]:
            key = str(item["question_number"])

            if key not in by_number:
                by_number[key] = item
                merged.append(item)
                continue

            existing = by_number[key]

            for language in ("en", "hi"):
                values = [
                    existing["question"].get(language),
                    item["question"].get(language),
                ]

                unique = list(
                    dict.fromkeys(
                        value.strip()
                        for value in values
                        if value and value.strip()
                    )
                )

                existing["question"][language] = (
                    "\n".join(unique) or None
                )

            known_options = {
                option["id"]
                for option in existing["options"]
            }

            existing["options"].extend(
                option
                for option in item["options"]
                if option["id"] not in known_options
            )

            existing["review_required"] = (
                existing["review_required"]
                or item["review_required"]
            )

        section["questions"] = merged

    return sections


def attach_media(sections, media, pages):
    page_map = {
        page["page"]: page
        for page in pages
    }

    for section in sections:
        for question in section["questions"]:
            page_number = question["source"]["page"]
            page = page_map.get(page_number)

            if not page or not page.get("lines"):
                continue

            number = int(question["question_number"])

            start_lines = [
                item
                for item in page["lines"]
                if QUESTION_RE.match(item[2])
                and int(
                    QUESTION_RE.match(item[2]).group(1)
                ) == number
            ]

            if not start_lines:
                question["review_required"] = True
                continue

            start_y = min(
                item[0] for item in start_lines
            )

            next_positions = []

            for y, x, text, bbox in page["lines"]:
                match = QUESTION_RE.match(text)

                if (
                    match
                    and int(match.group(1)) > number
                    and y > start_y
                ):
                    next_positions.append(y)

            end_y = min(
                next_positions,
                default=float("inf"),
            )

            for asset in media:
                if asset["source_page"] != page_number:
                    continue

                bbox = asset.get("bbox")

                if not bbox:
                    continue

                rect = fitz.Rect(bbox)

                if (
                    rect.y0 >= start_y - 8
                    and rect.y0 < end_y
                    and rect.y1 < end_y + 10
                ):
                    question["media"].append(
                        {
                            key: value
                            for key, value in asset.items()
                            if key != "bbox"
                        }
                    )


def run_conversion(
    conversion_id: str,
    source_files: list[Path],
    role_map: dict,
    root: Path,
):
    logger.info("Background conversion started: conversion=%s files=%d", conversion_id, len(source_files))
    try:
        update_job(
            conversion_id,
            status="processing",
            progress=5,
            stage="Extracting document content",
        )

        extracted = []

        for index, path in enumerate(source_files):
            logger.info("Extraction started: conversion=%s filename=%s", conversion_id, path.name)
            data = extract(
                path,
                root / "media",
            )

            role = role_map.get(
                path.name,
                "question_paper",
            )

            extracted.append(
                (path, data, role)
            )
            logger.info("Extraction complete: conversion=%s filename=%s pages=%d media=%d role=%s", conversion_id, path.name, data["page_count"] or len(data["pages"]), len(data["media"]), role)

            progress = 5 + int(
                35 * (index + 1) / len(source_files)
            )

            update_job(
                conversion_id,
                progress=progress,
                stage=f"Extracted {path.name}",
            )

        question_paper = next(
            (
                item
                for item in extracted
                if item[2] == "question_paper"
            ),
            extracted[0],
        )

        source_path, document_data, _ = question_paper

        update_job(
            conversion_id,
            progress=50,
            stage="Parsing question structure",
        )

        sections = parse_questions(
            document_data["pages"]
        )

        attach_media(
            sections,
            document_data["media"],
            document_data["pages"],
        )

        answer_text = "\n".join(
            page["text"]
            for path, data, role in extracted
            if role == "answer_key"
            for page in data["pages"]
        )

        answer_map = {}

        for line in answer_text.splitlines():
            match = re.match(
                r"^\s*(\d{1,3})\s*[).:-]\s*([A-Da-d1-4])\b",
                line.strip(),
            )

            if match:
                answer_map[int(match.group(1))] = (
                    match.group(2).upper()
                )

        matched = 0

        for section in sections:
            for question in section["questions"]:
                number = int(
                    question["question_number"]
                )

                answer = answer_map.get(number)

                if answer:
                    question["correct_answer"] = answer
                    matched += 1

        total_questions = sum(
            len(section["questions"])
            for section in sections
        )

        full_text = "\n".join(
            page["text"]
            for page in document_data["pages"]
        )

        languages = []

        if re.search(r"[A-Za-z]", full_text):
            languages.append("en")

        if re.search(r"[\u0900-\u097F]", full_text):
            languages.append("hi")

        result = {
            "document": {
                "title": document_data["title"],
                "total_questions": total_questions,
                "total_pages": document_data["page_count"],
                "source_filename": source_path.name,
                "source_format": (
                    source_path.suffix.lower().lstrip(".")
                ),
                "language": languages or ["unknown"],
                "answer_key_matched": matched,
                "answer_key_provided": bool(answer_text),
            },
            "sections": sections,
            "extraction_warnings": [
                "Some pages may contain legacy font encoding or scanned text. OCR and manual review may be required."
            ] if any(
                page.get("needs_ocr")
                for page in document_data["pages"]
            ) else [],
        }

        result_path = root / "result.json"

        result_path.write_text(
            json.dumps(
                result,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        update_job(
            conversion_id,
            status="completed",
            progress=100,
            stage="Conversion complete",
            error=None,
            result=result,
        )

    except Exception as error:
        logger.exception("Conversion failed: conversion=%s", conversion_id)
        update_job(
            conversion_id,
            status="failed",
            progress=100,
            stage="Conversion failed",
            error=str(error)[:500],
            result=None,
        )
