import json
import logging
import re
from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image
from docx import Document
import pytesseract

from app.storage import update_job
from app.services.answer_key import parse_answer_key

logger = logging.getLogger("docujson")


QUESTION_RE = re.compile(
    r"^\s*(?:Q(?:uestion)?\.?\s*)?(\d{1,3})\s*[).:](?=\s|$)\s*(.*)$",
    re.IGNORECASE,
)

OPTION_RE = re.compile(r"(?:\(([1-4])\)|\[([1-4])\]|([A-Da-d])[).:])\s*")

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
            hindi_count = len(re.findall(r"[\u0900-\u097f]", line))
            latin_count = len(re.findall(r"[A-Za-z]", line))
            if hindi_count >= latin_count:
                hindi.append(line)
            else:
                english.append(line)
                hindi_line = re.sub(r"[A-Za-z0-9]+", " ", line).strip()
                if re.search(r"[\u0900-\u097f]", hindi_line):
                    hindi.append(re.sub(r"\s+", " ", hindi_line))
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


def numbered_options(line: str) -> list[dict[str, str]]:
    """Read one or more labelled choices from a line that begins with an option marker."""
    leading = len(line) - len(line.lstrip())
    candidates = list(OPTION_RE.finditer(line))
    if not candidates or candidates[0].start() != leading:
        return []
    markers = [candidates[0]]
    previous = next(group for group in candidates[0].groups() if group).upper()
    for marker in candidates[1:]:
        current = next(group for group in marker.groups() if group).upper()
        follows = (previous.isdigit() and current.isdigit() and int(current) == int(previous) + 1) or (previous in "ABCD" and current in "ABCD" and "ABCD".index(current) == "ABCD".index(previous) + 1)
        if follows:
            markers.append(marker)
            previous = current
    options = []
    for index, marker in enumerate(markers):
        option_id = next(group for group in marker.groups() if group).upper()
        end = markers[index + 1].start() if index + 1 < len(markers) else len(line)
        option_text = line[marker.end():end].strip()
        options.append({"id": option_id, "text": option_text, "offset": marker.start()})
    return options


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


def _text_quality(text: str) -> float:
    if not text.strip():
        return 0.0
    suspicious = len(re.findall(r"[\ufffd\uf000-\uf8ff]", text))
    useful = len(re.findall(r"[A-Za-z\u0900-\u097f0-9]", text))
    return useful / max(1, len(text)) - min(0.8, suspicious / max(1, len(text)))


def _ocr_page(page):
    try:
        available = set(pytesseract.get_languages(config=""))
        if "eng" not in available:
            return "", ["OCR unavailable: Tesseract English language data is not installed."]
        language = "eng"
        warnings = []
        if "hin" in available:
            language += "+hin"
        else:
            warnings.append("Hindi OCR language pack is not installed; OCR fallback used English only.")
        pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        image = Image.open(BytesIO(pixmap.tobytes("png")))
        return pytesseract.image_to_string(image, lang=language, config="--psm 6"), warnings
    except Exception as error:
        logger.info("OCR unavailable for page: %s", error)
        return "", ["OCR fallback unavailable. Install Tesseract and its eng/hin language data to OCR this page."]


def extract_pdf(path: Path, media_dir: Path):
    document = fitz.open(path)

    pages = []
    media = []

    try:
        for page_index, page in enumerate(document):
            page_number = page_index + 1

            blocks = page.get_text("dict", sort=False).get("blocks", [])

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

            text_lines.sort(key=lambda item: (item[0], item[1]))
            page_width = page.rect.width
            left_lines, right_lines, full_lines = [], [], []
            for item in text_lines:
                rect = item[3]
                if rect.width >= page_width * 0.68 or (rect.x0 < page_width * 0.12 and rect.x1 > page_width * 0.88):
                    full_lines.append(item)
                elif rect.x0 + rect.width / 2 < page_width / 2:
                    left_lines.append(item)
                else:
                    right_lines.append(item)
            # Preserve full-width headings first, then read each column top-to-bottom.
            ordered_lines = sorted(full_lines, key=lambda item: (item[0], item[1])) + sorted(left_lines, key=lambda item: (item[0], item[1])) + sorted(right_lines, key=lambda item: (item[0], item[1]))
            page_text = "\n".join(item[2] for item in ordered_lines)

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

            original_text = page_text
            ocr_text = ""
            ocr_warnings = []
            ocr_used = False
            if needs_ocr:
                ocr_text, ocr_warnings = _ocr_page(page)
                if _text_quality(ocr_text) > _text_quality(original_text):
                    page_text = ocr_text.strip()
                    ocr_used = bool(page_text)

            pages.append(
                {
                    "page": page_number,
                    "width": page_width,
                    "text": page_text,
                    "source_text": original_text,
                    "ocr_text": ocr_text,
                    "ocr_used": ocr_used,
                    "ocr_warnings": ocr_warnings,
                    "needs_review": needs_ocr,
                    "lines": ordered_lines,
                    "columns": [
                        [item[2] for item in sorted(left_lines, key=lambda item: (item[0], item[1]))],
                        [item[2] for item in sorted(right_lines, key=lambda item: (item[0], item[1]))],
                    ] if left_lines and right_lines else None,
                    "words": [word for word in page.get_text("words")],
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
    has_section_headings = any(
        SECTION_RE.match(line.replace("\u00a0", " ").strip())
        for page in pages
        for line in page["text"].splitlines()
    )
    sections = []

    current_section = {
        "section_name": "General",
        "questions": [],
    }

    question = None
    expected_number = 1
    started_questions = not has_section_headings
    questions_by_number = {}
    orphaned_lines = []

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

        option_ids = {option["id"] for option in question["options"]}
        question["question_type"] = "mcq" if len(option_ids) == 4 else "subjective"
        question["review_required"] = not bool(raw_text) or (bool(question["options"]) and (len(option_ids) != 4 or any(not option["text"] for option in question["options"])))
        number = int(question["question_number"])
        question.pop("_option_started", None)
        question.pop("_option_anchors", None)
        existing = questions_by_number.get(number)
        if existing is None:
            questions_by_number[number] = question
            current_section["questions"].append(question)
        else:
            for language in ("en", "hi"):
                first = existing["question"].get(language)
                second = question["question"].get(language)
                if not second or second in (first or ""):
                    continue
                if not first or first in second:
                    existing["question"][language] = second
                elif language == "en" and len(second) > len(first) * 2 and all(len(line.strip()) <= 12 for line in first.splitlines()):
                    existing["question"][language] = second
                else:
                    existing["question"][language] = "\n".join((first, second))
            for option in question["options"]:
                prior = next((item for item in existing["options"] if item["id"] == option["id"]), None)
                if prior is None:
                    existing["options"].append(option)
                elif prior["text"] != option["text"]:
                    prior_hindi = bool(re.search(r"[\u0900-\u097f]", prior["text"]))
                    option_hindi = bool(re.search(r"[\u0900-\u097f]", option["text"]))
                    if re.search(r"[A-Za-z]", option["text"]) and not option_hindi and prior_hindi:
                        prior["text"] = option["text"]
            existing["review_required"] = existing["review_required"] or question["review_required"]
            if len({option["id"] for option in existing["options"]}) == 4:
                existing["question_type"] = "mcq"

        question = None

    def flush_section():
        nonlocal started_questions
        flush_question()

        if current_section["questions"]:
            sections.append(current_section.copy())

    for page in pages:
        if expected_number > 50:
            break
        page_number = page["page"]
        positioned_lines = page.get("lines", [])
        if positioned_lines and not page.get("ocr_used"):
            page_lines = [(item[2], item[3]) for item in positioned_lines]
        else:
            page_lines = [(line, None) for line in page["text"].splitlines()]
        page_heading = next(
            (match for line, _ in page_lines if (match := SECTION_RE.match(line.replace("\u00a0", " ").strip()))),
            None,
        )
        if page_heading:
            page_section_name = f"Section {page_heading.group(1)}"
            if current_section["section_name"] != page_section_name:
                flush_section()
                current_section = {"section_name": page_section_name, "questions": []}
            started_questions = True

        for line, line_bbox in page_lines:
            text = line.replace("\u00a0", " ").strip()

            if not text:
                continue

            if re.search(r"(?i)join telegram|telegram:|\bTG:\s*@|\bPHASE\s*-|\b\d{12,}\b|\b\d{4}[A-Z]{2,}\d{6,}\b|\b\d{2}-\d{2}-\d{4}\b|ALLEN\s*®?", text):
                continue

            section_match = SECTION_RE.match(text)

            if section_match:
                section_name = f"Section {section_match.group(1)}"
                if current_section["section_name"] != section_name:
                    flush_section()
                    current_section = {"section_name": section_name, "questions": []}
                started_questions = True
                continue

            question_match = QUESTION_RE.match(text)

            if question_match:
                if not started_questions:
                    continue
                number = int(question_match.group(1))
                initial_text = question_match.group(2).strip()
                explicitly_labeled = bool(re.match(r"^\s*(?:Q(?:uestion)?\.?\s*)\d", text, re.IGNORECASE))
                is_next_question = number == expected_number or (
                    expected_number < number <= 50
                    and bool(initial_text)
                    and (number - expected_number <= 3 or explicitly_labeled)
                )
                existing_question = questions_by_number.get(number)
                existing_bbox = existing_question.get("_source_bbox") if existing_question else None
                is_parallel_copy = bool(
                    existing_question
                    and existing_question["source"]["page"] == page_number
                    and existing_bbox
                    and line_bbox is not None
                    and abs(existing_bbox[0] - line_bbox.x0) > page.get("width", 0) * 0.35
                )
                if not is_next_question and not is_parallel_copy:
                    if question is not None and initial_text:
                        question["_lines"].append(text)
                    continue

                flush_question()
                if is_next_question:
                    expected_number = number + 1
                    carried_lines = [item[0] for item in orphaned_lines]
                    orphaned_lines.clear()
                else:
                    carried_lines = []
                    orphaned_lines.clear()

                question = {
                    "question_id": f"q{number}",
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
                    "_source_bbox": list(line_bbox) if line_bbox is not None else None,
                    "_option_started": False,
                    "_option_anchors": {},
                    "media": [],
                    "review_required": bool(page.get("needs_review")),
                    "_lines": carried_lines + ([initial_text] if initial_text else []),
                }

                continue

            if question is None:
                continue

            option_lines = numbered_options(text)

            if option_lines:
                if orphaned_lines:
                    question["review_required"] = True
                    orphaned_lines.clear()
                for option in option_lines:
                    option_id = option["id"]
                    option_text = option["text"]
                    existing_option = next((item for item in question["options"] if item["id"] == option["id"]), None)
                    if existing_option is None:
                        question["options"].append({"id": option_id, "text": option_text})
                        if line_bbox is not None:
                            approximate_x = line_bbox.x0 + (option["offset"] / max(1, len(text))) * line_bbox.width
                            question["_option_anchors"][option_id] = (approximate_x, line_bbox.y0)
                    elif option_text and existing_option["text"] != option_text:
                        old_has_latin = bool(re.search(r"[A-Za-z]", existing_option["text"]))
                        new_has_latin = bool(re.search(r"[A-Za-z]", option_text))
                        if new_has_latin and not old_has_latin:
                            existing_option["text"] = option_text
                        elif old_has_latin == new_has_latin:
                            question["review_required"] = True
                    question["_option_started"] = True
                continue

            answer_match = ANSWER_RE.match(text)

            if answer_match:
                question["correct_answer"] = (
                    answer_match.group(1).strip()
                )
                continue

            if question.get("_option_started"):
                if question.get("options"):
                    if line_bbox is not None and question.get("_option_anchors"):
                        option_id = min(
                            question["_option_anchors"],
                            key=lambda key: abs(question["_option_anchors"][key][0] - line_bbox.x0)
                            + abs(question["_option_anchors"][key][1] - line_bbox.y0),
                        )
                        anchor_y = question["_option_anchors"][option_id][1]
                        if abs(anchor_y - line_bbox.y0) > 24:
                            orphaned_lines.append((text, line_bbox))
                            continue
                    else:
                        option_id = question["options"][-1]["id"]
                    option = next((item for item in question["options"] if item["id"] == option_id), None)
                    if option is not None:
                        option["text"] = " ".join(part for part in (option["text"], text) if part)
                    continue
            question["_lines"].append(text)

        if question is not None and int(question["question_number"]) == 50:
            flush_question()

    flush_question()

    if current_section["questions"]:
        sections.append(current_section)

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
            source_bbox = question.get("_source_bbox")

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

            start_y = source_bbox[1] if source_bbox else min(item[0] for item in start_lines)
            start_x = source_bbox[0] if source_bbox else min(item[1] for item in start_lines)

            next_positions = []

            for y, x, text, bbox in page["lines"]:
                match = QUESTION_RE.match(text)

                same_column = abs(x - start_x) < page.get("width", 100000) * 0.18
                if match and int(match.group(1)) > number and y > start_y and same_column:
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
                    and (not source_bbox or abs((rect.x0 + rect.x1) / 2 - start_x) < page.get("width", 100000) * 0.30)
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
    source_name_map: dict | None = None,
):
    source_name_map = source_name_map or {}
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
        original_source_name = source_name_map.get(source_path.name, source_path.name)
        title = document_data["title"]
        if title == source_path.stem:
            title = Path(original_source_name).stem

        debug_pages = [
            {
                "page": page["page"],
                "extracted_text": page.get("source_text", page.get("text", "")),
                "ocr_text": page.get("ocr_text", ""),
                "ocr_used": page.get("ocr_used", False),
                "needs_review": page.get("needs_review", False),
                "warnings": page.get("ocr_warnings", []),
            }
            for page in document_data["pages"]
        ]
        (root / "extraction_debug.json").write_text(
            json.dumps(debug_pages, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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
        for section in sections:
            for parsed_question in section["questions"]:
                parsed_question.pop("_source_bbox", None)

        answer_key_items = [data for _, data, role in extracted if role == "answer_key"]
        answer_parse = parse_answer_key([
            page
            for data in answer_key_items
            for page in data["pages"]
        ]) if answer_key_items else {"answers": {}, "entry_count": 0, "warnings": []}
        answer_map = answer_parse["answers"]
        indexed_questions = {}
        for section in sections:
            for parsed_question in section["questions"]:
                indexed_questions.setdefault(int(parsed_question["question_number"]), []).append(parsed_question)

        matched = 0
        for number, answer in answer_map.items():
            matches = indexed_questions.get(number, [])
            if len(matches) != 1:
                for parsed_question in matches:
                    parsed_question["review_required"] = True
                continue
            parsed_question = matches[0]
            option_ids = [option["id"] for option in parsed_question["options"]]
            normalized = answer
            if option_ids and all(option_id.isdigit() for option_id in option_ids):
                normalized = str("ABCD".find(answer) + 1) if answer in "ABCD" else answer
            elif option_ids and all(option_id in "ABCD" for option_id in option_ids):
                normalized = "ABCD"[int(answer) - 1] if answer.isdigit() else answer
            if normalized in {"1", "2", "3", "4", "A", "B", "C", "D"}:
                parsed_question["correct_answer"] = normalized
                matched += 1

        missing_answers = sorted(set(indexed_questions) - set(answer_map)) if answer_key_items else []
        for number in missing_answers:
            for parsed_question in indexed_questions[number]:
                parsed_question["review_required"] = True

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

        extraction_warnings = list(answer_parse["warnings"])
        for page in document_data["pages"]:
            extraction_warnings.extend(page.get("ocr_warnings", []))
        if missing_answers:
            extraction_warnings.append(f"No unambiguous answer-key entry found for questions: {', '.join(map(str, missing_answers))}.")
        result = {
            "document": {
                "title": title,
                "total_questions": total_questions,
                "total_pages": document_data["page_count"],
                "source_filename": original_source_name,
                "source_format": (
                    Path(original_source_name).suffix.lower().lstrip(".")
                ),
                "language": languages or ["unknown"],
                "answer_key_matched": matched,
                "answer_key_provided": bool(answer_key_items),
                "answer_key_extracted": answer_parse["entry_count"],
            },
            "sections": sections,
            "extraction_warnings": extraction_warnings + ([
                "Some pages may contain legacy font encoding or scanned text. OCR and manual review may be required."
            ] if any(
                page.get("needs_ocr")
                for page in document_data["pages"]
            ) else []),
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
