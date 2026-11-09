import json
import logging
import os
import re
from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image, ImageOps
from docx import Document
import pytesseract

from app.config import settings
from app.models import DocumentResult
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
                # A mixed source line is retained intact in its dominant script field;
                # stripping the Latin/math tokens here was corrupting formulas.
                hindi.append(line)
            else:
                english.append(line)
        elif has_hindi:
            hindi.append(line)
        elif has_english:
            english.append(line)

    def reflow(lines: list[str]) -> str | None:
        paragraphs: list[str] = []
        for line in lines:
            if not paragraphs:
                paragraphs.append(line)
                continue
            previous = paragraphs[-1]
            math_symbols = len(re.findall(r"[∫∑∏√∛∞≠≤≥≈≡∈⊂×÷±∓→←↔⇒⇔∠⟂∥∇∂ΔΣΩαβγθφλμπω^_=]", line))
            prose_letters = len(re.findall(r"[A-Za-z\u0900-\u097f]", line))
            previous_math = len(re.findall(r"[∫∑∏√∛∞≠≤≥≈≡∈⊂×÷±∓→←↔⇒⇔∠⟂∥∇∂ΔΣΩαβγθφλμπω^_=]", previous))
            if math_symbols >= 2 and prose_letters <= 8 or previous_math >= 2 and len(re.findall(r"[A-Za-z\u0900-\u097f]", previous)) <= 8:
                paragraphs.append(line)
            else:
                paragraphs[-1] = f"{previous} {line}"
        return "\n".join(paragraphs) or None

    if english or hindi:
        return {
            "en": reflow(english),
            "hi": reflow(hindi),
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


def _option_for_position(anchors: dict, line_bbox, max_vertical_gap: float = 42):
    if line_bbox is None or not anchors:
        return None
    x, y = line_bbox.x0, line_bbox.y0
    nearby = [(option_id, point) for option_id, point in anchors.items() if abs(point[1] - y) <= max_vertical_gap]
    if not nearby:
        return None
    row_y = min((point[1] for _, point in nearby), key=lambda anchor_y: abs(anchor_y - y))
    row = sorted(
        ((option_id, point[0]) for option_id, point in nearby if abs(point[1] - row_y) <= 10),
        key=lambda item: item[1],
    )
    preceding = [item for item in row if item[1] <= x + 5]
    if preceding:
        return preceding[-1][0]
    if row and x >= row[0][1] - 24:
        return row[0][0]
    return None


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
    useful = len(re.findall(r"[A-Za-z\u0900-\u097f0-9\u00a0-\u024f\u0370-\u03ff\u2000-\u2bff]", text))
    controls = len(re.findall(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", text))
    return useful / max(1, len(text)) - min(0.8, (suspicious + controls) / max(1, len(text)))


def _ocr_page(page, page_number: int | None = None, media_dir: Path | None = None):
    """OCR only a page already judged weak; retain the 300-DPI render as diagnostic evidence."""
    warnings = []
    try:
        tesseract_cmd = settings.tesseract_cmd
        if not tesseract_cmd and os.name == "nt":
            program_files = Path(os.environ.get("PROGRAMFILES", r"C:\Program Files"))
            standard_install = program_files / "Tesseract-OCR" / "tesseract.exe"
            if standard_install.is_file():
                tesseract_cmd = str(standard_install)
        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
        requested = [language.strip() for language in settings.ocr_languages.split("+") if language.strip()]
        tessdata = settings.tessdata_prefix
        if tessdata:
            os.environ["TESSDATA_PREFIX"] = tessdata
        try:
            pytesseract.get_tesseract_version()
        except Exception as error:
                return "", [f"OCR unavailable: Tesseract executable could not be started ({type(error).__name__})."], []
        try:
            available = set(pytesseract.get_languages(config=""))
        except Exception as error:
                return "", [f"OCR unavailable: trained-language data could not be read ({type(error).__name__})."], []
        selected = [language for language in requested if language in available]
        if "eng" in available and "eng" not in selected:
            selected.insert(0, "eng")
        missing = [language for language in requested if language not in available]
        if missing:
            warnings.append(f"Requested OCR language data is unavailable: {', '.join(missing)}.")
        if not selected:
            return "", warnings + ["OCR unavailable: no requested Tesseract languages are installed."], []

        dpi = max(150, min(450, int(settings.ocr_dpi)))
        pixmap = page.get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72), alpha=False)
        image = ImageOps.autocontrast(Image.open(BytesIO(pixmap.tobytes("png"))).convert("L"))
        if media_dir is not None and page_number is not None:
            media_dir.mkdir(parents=True, exist_ok=True)
            evidence_path = media_dir / f"evidence_page_{page_number}.png"
            image.save(evidence_path, format="PNG")
            warnings.append(f"OCR source image retained as media/{evidence_path.name}.")
        language = "+".join(selected)
        config = f"--psm 3 --dpi {dpi}"
        ocr_data = pytesseract.image_to_data(
            image,
            lang=language,
            config=config,
            output_type=pytesseract.Output.DICT,
        )
        line_groups = {}
        confidences = []
        scale = 72 / dpi
        for index, value in enumerate(ocr_data.get("text", [])):
            value = str(value).strip()
            if not value:
                continue
            try:
                confidence = float(ocr_data["conf"][index])
            except (ValueError, TypeError, IndexError):
                confidence = -1
            if confidence >= 0:
                confidences.append(confidence)
            key = tuple(ocr_data.get(name, [0] * len(ocr_data["text"]))[index] for name in ("page_num", "block_num", "par_num", "line_num"))
            left = float(ocr_data["left"][index]) * scale
            top = float(ocr_data["top"][index]) * scale
            right = left + float(ocr_data["width"][index]) * scale
            bottom = top + float(ocr_data["height"][index]) * scale
            row = line_groups.setdefault(key, {"words": [], "bbox": [left, top, right, bottom]})
            row["words"].append(value)
            row["bbox"] = [min(row["bbox"][0], left), min(row["bbox"][1], top), max(row["bbox"][2], right), max(row["bbox"][3], bottom)]
        ocr_lines = []
        for row in line_groups.values():
            bbox = fitz.Rect(row["bbox"])
            ocr_lines.append((bbox.y0, bbox.x0, " ".join(row["words"]), bbox, []))
        ocr_lines.sort(key=lambda item: (item[0], item[1]))
        if confidences and sum(confidences) / len(confidences) < 45:
            warnings.append("OCR confidence is low; OCR text was retained for review.")
        return "\n".join(item[2] for item in ocr_lines), warnings, ocr_lines
    except Exception as error:
        logger.info("OCR unavailable for page: %s", error)
        return "", warnings + [f"OCR failed: {type(error).__name__}: {error}"], []


def _line_text_from_spans(spans: list[dict]) -> str:
    """Join decoded span text in geometric order without deleting math or Unicode glyphs."""
    ordered = sorted(spans, key=lambda span: (span.get("bbox", [0, 0])[0], span.get("bbox", [0, 0])[1]))
    pieces: list[str] = []
    previous = None
    for span in ordered:
        value = repair_pdf_mojibake(span.get("text", ""))
        if not value:
            continue
        if previous is not None and pieces:
            gap = float(span.get("bbox", [0])[0]) - float(previous.get("bbox", [0, 0, 0, 0])[2])
            size = max(float(span.get("size", 0) or 0), float(previous.get("size", 0) or 0))
            if gap > max(1.5, size * 0.18) and not pieces[-1].endswith((" ", "\t")) and not value.startswith((" ", "\t")):
                pieces.append(" ")
        pieces.append(value)
        previous = span
    return "".join(pieces).strip()


def repair_pdf_mojibake(text: str) -> str:
    """Repair recognizable UTF-8 bytes decoded as Windows-1252; retain raw spans separately."""
    marker_pattern = r"(?:\u00e0\u00a4|\u00e0\u00a5|\u00e2[\u20ac-\u20bf]|\u00ce[\x80-\xff]|\u00cf[\x80-\xff]|\u00c2[\x80-\xff])"
    if not text or not re.search(marker_pattern, text):
        return text
    try:
        repaired = text.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    markers = re.compile(marker_pattern)
    return repaired if len(markers.findall(repaired)) < len(markers.findall(text)) else text


def _reconstruct_stacked_fractions(lines):
    """Join compact numerator/denominator text only when page geometry aligns them."""
    consumed = set()
    reconstructed = []
    for index, line in enumerate(lines):
        if index in consumed:
            continue
        y, x, text, bbox, spans = line
        token = text.strip()
        if not re.fullmatch(r"[A-Za-z0-9\u0370-\u03ff]+", token) or not re.search(r"\d", token):
            reconstructed.append(line)
            continue
        candidates = []
        for next_index in range(index + 1, len(lines)):
            if next_index in consumed:
                continue
            next_y, next_x, next_text, next_bbox, next_spans = lines[next_index]
            gap = next_y - y
            if gap > 28:
                break
            denominator = next_text.strip()
            if not re.fullmatch(r"[A-Za-z0-9\u0370-\u03ff]+", denominator) or not re.search(r"\d", denominator):
                continue
            if abs((bbox.x0 + bbox.x1) / 2 - (next_bbox.x0 + next_bbox.x1) / 2) <= 9 and 4 <= gap <= 28:
                candidates.append((gap, next_index, denominator, next_bbox, next_spans))
        if not candidates:
            reconstructed.append(line)
            continue
        _, denominator_index, denominator, denominator_bbox, denominator_spans = min(candidates)
        combined_bbox = bbox | denominator_bbox
        combined = f"{token}/{denominator}"
        reconstructed.append((combined_bbox.y0, combined_bbox.x0, combined, combined_bbox, spans + denominator_spans))
        consumed.add(denominator_index)
    # Keep the caller's detected column reading order; a global y-sort would
    # interleave bilingual columns after the geometry-based fraction pass.
    return reconstructed


def extract_pdf(path: Path, media_dir: Path):
    document = fitz.open(path)

    pages = []
    media = []

    try:
        for page_index, page in enumerate(document):
            page_number = page_index + 1

            blocks = page.get_text("dict", sort=False).get("blocks", [])
            raw_blocks = page.get_text("rawdict", sort=False).get("blocks", [])
            native_text = page.get_text("text", sort=False)
            drawings = page.get_drawings()

            text_lines = []

            for block_index, block in enumerate(blocks):
                if block.get("type") != 0:
                    continue

                raw_block = raw_blocks[block_index] if block_index < len(raw_blocks) else {}
                raw_lines = raw_block.get("lines", [])
                for line_index, line in enumerate(block.get("lines", [])):
                    spans = line.get("spans", [])
                    raw_line = raw_lines[line_index] if line_index < len(raw_lines) else {}
                    raw_spans = raw_line.get("spans", [])
                    detailed_spans = []
                    for span_index, span in enumerate(spans):
                        raw_span = raw_spans[span_index] if span_index < len(raw_spans) else {}
                        chars = raw_span.get("chars", [])
                        decoded = "".join(char.get("c", "") for char in chars) if chars else span.get("text", "")
                        detailed_spans.append({"text": decoded, "bbox": list(span.get("bbox", ())), "origin": list(span.get("origin", ())), "font": span.get("font"), "size": span.get("size"), "flags": span.get("flags"), "chars": [{"c": char.get("c", ""), "bbox": list(char.get("bbox", ())), "origin": list(char.get("origin", ()))} for char in chars]})
                    text = _line_text_from_spans(detailed_spans)

                    if not text:
                        continue

                    bbox = fitz.Rect(line["bbox"])

                    text_lines.append(
                        (
                            bbox.y0,
                            bbox.x0,
                            text,
                            bbox,
                            detailed_spans,
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
            native_ordered_lines = list(ordered_lines)
            ordered_lines = _reconstruct_stacked_fractions(ordered_lines)
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
            suspicious_glyphs = len(re.findall(r"[\ufffd\uF000-\uF8FF]", page_text))
            useful_ratio = len(re.findall(r"[\w\u0900-\u097f]", page_text, flags=re.UNICODE)) / max(1, len(page_text))
            needs_ocr = bool(len(page_text.strip()) < 60 or suspicious_glyphs >= 2 or (len(page_text) > 180 and useful_ratio < 0.42))

            original_text = page_text
            ocr_text = ""
            ocr_warnings = []
            ocr_lines = []
            ocr_used = False
            if needs_ocr:
                ocr_text, ocr_warnings, ocr_lines = _ocr_page(page, page_number, media_dir)
                if ocr_text.strip() and _text_quality(original_text) < 0.55 and _text_quality(ocr_text) > _text_quality(original_text) + 0.08:
                    full_ocr, left_ocr, right_ocr = [], [], []
                    for ocr_line in ocr_lines:
                        rect = ocr_line[3]
                        if rect.width >= page_width * 0.68:
                            full_ocr.append(ocr_line)
                        elif (rect.x0 + rect.x1) / 2 < page_width / 2:
                            left_ocr.append(ocr_line)
                        else:
                            right_ocr.append(ocr_line)
                    ordered_lines = sorted(full_ocr, key=lambda item: (item[0], item[1])) + sorted(left_ocr, key=lambda item: (item[0], item[1])) + sorted(right_ocr, key=lambda item: (item[0], item[1]))
                    page_text = "\n".join(item[2] for item in ordered_lines)
                    ocr_used = bool(page_text)
                    ocr_warnings.append("OCR text replaced native page text because native extraction quality was poor; both versions remain in debug data.")

            pages.append(
                {
                    "page": page_number,
                    "width": page_width,
                    "height": page.rect.height,
                    "text": page_text,
                    "source_text": original_text,
                    "native_text": native_text,
                    "ocr_text": ocr_text,
                    "ocr_used": ocr_used,
                    "ocr_warnings": ocr_warnings,
                    "needs_review": needs_ocr,
                    "lines": ordered_lines,
                    "native_lines": native_ordered_lines,
                    "ocr_lines": ocr_lines,
                    "spans": [span for _, _, _, _, spans in native_ordered_lines for span in spans],
                    "span_lines": [{"bbox": list(bbox), "text": text, "spans": spans} for _, _, text, bbox, spans in native_ordered_lines],
                    "fonts": [list(font) for font in page.get_fonts(full=True)],
                    "columns": [
                        [item[2] for item in sorted(left_lines, key=lambda item: (item[0], item[1]))],
                        [item[2] for item in sorted(right_lines, key=lambda item: (item[0], item[1]))],
                    ] if left_lines and right_lines else None,
                    "words": [word for word in page.get_text("words")],
                    "fraction_rules": [
                        list(drawing["rect"])
                        for drawing in drawings
                        if fitz.Rect(drawing["rect"]).height <= 1.5
                        and fitz.Rect(drawing["rect"]).width >= 4
                    ],
                    "needs_ocr": needs_ocr,
                }
            )

            evidence_path = media_dir / f"evidence_page_{page_number}.png"
            if needs_ocr and evidence_path.is_file():
                media.append({
                    "asset_id": f"evidence_page_{page_number}",
                    "filename": evidence_path.name,
                    "type": "diagnostic_page",
                    "source_page": page_number,
                    "bbox": list(page.rect),
                    "content": None,
                })

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

            for drawing in drawings:
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
    pre_anchor_lines = {}

    def flush_question():
        nonlocal question

        if question is None:
            return

        question["options"].sort(key=lambda option: (not str(option["id"]).isdigit(), int(option["id"]) if str(option["id"]).isdigit() else str(option["id"])))

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
        question["original_text"] = raw_text
        question["reconstructed_text"] = question["question"]

        question["marks"] = marks

        option_ids = {option["id"] for option in question["options"]}
        is_mcq = bool(question.get("_option_started") or question["options"])
        question["question_type"] = "mcq" if is_mcq else "subjective"
        reasons = list(question.get("review_reasons", []))
        if not raw_text:
            reasons.append("Question text could not be extracted.")
        if is_mcq and len(option_ids) != 4:
            reasons.append(f"Expected four choices but recovered {len(option_ids)} distinct option labels.")
        if any(not option["text"].strip() and not option.get("media") for option in question["options"]):
            reasons.append("One or more options have neither readable text nor associated media.")
        if any(
            not option.get("media")
            and re.fullmatch(r"[\s\W_]{1,8}", option.get("text", ""), flags=re.UNICODE)
            and re.search(r"[∫√→←↔∇=+−×÷^]", option.get("text", ""))
            for option in question["options"]
        ):
            reasons.append("An option contains only isolated mathematical symbols and may be truncated.")
        if question.get("_page_needs_review"):
            reasons.append("The source page has an extraction or OCR warning.")
        compact_math = re.search(r"(?:[∫√→←↔∇]|[=+*/^])\s*(?:[=+*/^]|$)", raw_text)
        if compact_math:
            reasons.append("Mathematical notation may be fragmented in the extracted text.")
        mixed_script_lines = []
        for line in raw_text.splitlines():
            hindi_count = len(re.findall(r"[\u0900-\u097f]", line))
            latin_count = len(re.findall(r"[A-Za-z]", line))
            if hindi_count >= 3 and latin_count >= 3 and max(hindi_count, latin_count) <= min(hindi_count, latin_count) * 3:
                mixed_script_lines.append(line)
        if mixed_script_lines:
            reasons.append("A source line mixes Hindi and Latin text; it was preserved intact for manual language review.")
        question["review_reasons"] = list(dict.fromkeys(reasons))
        question["review_required"] = bool(question["review_reasons"])
        number = int(question["question_number"])
        question.pop("_option_started", None)
        question.pop("_option_anchors", None)
        question.pop("_page_needs_review", None)
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
            existing["review_reasons"] = list(dict.fromkeys(existing.get("review_reasons", []) + question.get("review_reasons", [])))
            existing["review_required"] = bool(existing["review_reasons"])
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
        if positioned_lines:
            page_lines = [(item[2], item[3]) for item in positioned_lines]
        else:
            page_lines = [(line, None) for line in page["text"].splitlines()]
        positioned_anchors = []
        page_option_anchors = []
        for anchor_line, anchor_bbox in page_lines:
            anchor_match = QUESTION_RE.match(anchor_line.replace("\u00a0", " ").strip())
            if anchor_match and anchor_bbox is not None:
                positioned_anchors.append((int(anchor_match.group(1)), anchor_bbox.y0, anchor_bbox.x0))
            if anchor_bbox is not None:
                for parsed_option in numbered_options(anchor_line.replace("\u00a0", " ").strip()):
                    option_x = anchor_bbox.x0 + (parsed_option["offset"] / max(1, len(anchor_line))) * anchor_bbox.width
                    page_option_anchors.append((parsed_option["id"], option_x, anchor_bbox.y0))
        pending_option_math = {}
        pending_option_prefix = {}
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
                    and (number - expected_number <= 3 or explicitly_labeled)
                )
                existing_question = questions_by_number.get(number)
                existing_bbox = (
                    existing_question.get("_source_bbox") or existing_question.get("source", {}).get("bbox")
                    if existing_question else None
                )
                is_parallel_copy = bool(
                    existing_question
                    and existing_question["source"]["page"] == page_number
                    and existing_bbox
                    and line_bbox is not None
                    and abs(existing_bbox[0] - line_bbox.x0) > page.get("width", 0) * 0.35
                )
                if (
                    not is_parallel_copy
                    and question is not None
                    and int(question["question_number"]) == number
                    and question.get("_source_bbox")
                    and line_bbox is not None
                    and abs(question["_source_bbox"][0] - line_bbox.x0) > page.get("width", 0) * 0.35
                ):
                    is_parallel_copy = True
                if not is_next_question and not is_parallel_copy:
                    # Numbered anchors delimit regions even when page/column order skips a question.
                    # Never fold a recognized next-question heading into the current body/options.
                    continue

                flush_question()
                if is_next_question:
                    expected_number = number + 1
                    carried_lines = []
                    orphaned_lines.clear()
                else:
                    carried_lines = []
                    orphaned_lines.clear()
                pending_option_math.clear()
                pending_option_prefix.clear()

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
                        "bbox": list(line_bbox) if line_bbox is not None else None,
                    },
                    "_source_bbox": list(line_bbox) if line_bbox is not None else None,
                    "_option_started": False,
                    "_option_anchors": {},
                    "media": [],
                    "review_required": bool(page.get("needs_review")),
                    "review_reasons": (["The source page has an extraction or OCR warning."] if page.get("needs_review") else []),
                    "_page_needs_review": bool(page.get("needs_review")),
                    "_lines": carried_lines + pre_anchor_lines.pop(number, []) + ([initial_text] if initial_text else []),
                }

                continue

            if question is None:
                continue

            # Some PDFs place the body line a few points above its printed number.
            # Hold it for the upcoming same-column anchor instead of leaking it into
            # the prior question's final option.
            if line_bbox is not None:
                nearby_question_gap = 12
                math_fragment = bool(
                    len(text) <= 36
                    and (
                        re.search(r"(?:\u2192|\u20d7|\^|\u00e2\u2020\u2019|\u00e2\u0192\u2014)", text)
                        or re.fullmatch(r"(?:d[xy]|d2[xy]|[xy]2|[xy]_[xy])", text, re.IGNORECASE)
                    )
                )
                if question.get("_option_started") and math_fragment:
                    nearby_question_gap = 38
                formula_fragment = math_fragment or bool(
                    re.fullmatch(r"\([^)]{1,30}\)", text)
                    and re.search(r"[\d=^+*/\u2212\u00d7\u221a]", text)
                )
                upcoming = [
                    (anchor_number, anchor_y, anchor_x)
                    for anchor_number, anchor_y, anchor_x in positioned_anchors
                    if anchor_y >= line_bbox.y0 and anchor_y - line_bbox.y0 <= nearby_question_gap
                    and anchor_number > int(question["question_number"])
                    and question.get("_source_bbox")
                    and abs(anchor_x - question["_source_bbox"][0]) < page.get("width", 100000) * 0.18
                ]
                if upcoming and (not text.startswith(("(", "[")) or formula_fragment):
                    target_number = min(upcoming, key=lambda item: item[1])[0]
                    pre_anchor_lines.setdefault(target_number, []).append(text)
                    continue

            if line_bbox is not None and question.get("_source_bbox"):
                question_side = (question["_source_bbox"][0] + question["_source_bbox"][2]) / 2 >= page.get("width", 0) / 2
                line_side = (line_bbox.x0 + line_bbox.x1) / 2 >= page.get("width", 0) / 2
                if question_side != line_side:
                    continue

            option_lines = numbered_options(text)

            isolated_numeric = bool(re.fullmatch(r"\d{1,3}", text))
            option_formula_prefix = bool(
                len(text) <= 24
                and re.search(r"[\d/=+^\u2212\u00b1\u00d7\u00f7\u221a\u222b\u2192\u2190]", text)
                and not re.search(r"[\u0900-\u097f]{2,}|\b(?:the|and|which|what|find|then)\b", text, re.IGNORECASE)
            )
            if option_formula_prefix and not option_lines and line_bbox is not None and not question.get("_option_started"):
                future_question_y = min(
                    (anchor_y for anchor_number, anchor_y, anchor_x in positioned_anchors
                     if anchor_number > int(question["question_number"])
                     and anchor_y > line_bbox.y0
                     and abs(anchor_x - question["_source_bbox"][0]) < page.get("width", 100000) * 0.18),
                    default=float("inf"),
                )
                candidate_anchors = {
                    option_id: (x, y)
                    for option_id, x, y in page_option_anchors
                    if line_bbox.y0 <= y <= line_bbox.y0 + 18 and y < future_question_y
                    and (x < page.get("width", 0) / 2)
                    == ((question["_source_bbox"][0] + question["_source_bbox"][2]) / 2 < page.get("width", 0) / 2)
                }
                candidate_id = _option_for_position(candidate_anchors, line_bbox, max_vertical_gap=18)
                if candidate_id:
                    pending_option_prefix.setdefault(candidate_id, []).append((text, line_bbox))
                    continue
            if (
                not option_lines
                and line_bbox is not None
                and not question.get("_option_started")
                and re.fullmatch(r"[\d\s^_=+\-×÷√∫→←()/.]+", text)
                and (len(text) <= 5 or not re.search(r"[A-Za-z\u0900-\u097f]", text))
            ):
                future_question_y = min(
                    (anchor_y for anchor_number, anchor_y, anchor_x in positioned_anchors
                     if anchor_number > int(question["question_number"])
                     and anchor_y > line_bbox.y0
                     and abs(anchor_x - question["_source_bbox"][0]) < page.get("width", 100000) * 0.18),
                    default=float("inf"),
                )
                candidate_anchors = {
                    option_id: (x, y)
                    for option_id, x, y in page_option_anchors
                    if line_bbox.y0 <= y <= line_bbox.y0 + 18 and y < future_question_y
                    and (x < page.get("width", 0) / 2)
                    == ((question["_source_bbox"][0] + question["_source_bbox"][2]) / 2 < page.get("width", 0) / 2)
                }
                candidate_id = _option_for_position(candidate_anchors, line_bbox, max_vertical_gap=18)
                if candidate_id and isolated_numeric:
                    # A compact numeric glyph aligned over an option-row number may be
                    # a stacked numerator; defer it until the denominator is observed.
                    pending_option_math.setdefault(candidate_id, []).append((text, line_bbox))
                    continue

            if option_lines:
                if orphaned_lines:
                    question["review_required"] = True
                    orphaned_lines.clear()
                for option in option_lines:
                    option_id = option["id"]
                    option_text = option["text"]
                    marker_x = line_bbox.x0 + (option["offset"] / max(1, len(text))) * line_bbox.width if line_bbox is not None else None
                    marker_bbox = None
                    if line_bbox is not None and marker_x is not None:
                        marker_width = max(7, min(18, line_bbox.height * 0.8))
                        marker_bbox = fitz.Rect(marker_x, line_bbox.y0, min(line_bbox.x1, marker_x + marker_width), line_bbox.y1)
                    existing_option = next((item for item in question["options"] if item["id"] == option["id"]), None)
                    if existing_option is None:
                        question["options"].append({
                            "id": option_id,
                            "text": option_text,
                            "original_text": option_text,
                            "media": [],
                            "source": {"page": page_number, "bbox": list(marker_bbox) if marker_bbox is not None else None, "content_bboxes": [list(line_bbox)] if line_bbox is not None else []},
                            "review_required": not bool(option_text),
                        })
                        if marker_x is not None:
                            question["_option_anchors"][option_id] = (marker_x, line_bbox.y0)
                    elif option_text and existing_option["text"] != option_text:
                        old_has_latin = bool(re.search(r"[A-Za-z]", existing_option["text"]))
                        new_has_latin = bool(re.search(r"[A-Za-z]", option_text))
                        if new_has_latin and not old_has_latin:
                            existing_option["text"] = option_text
                        elif old_has_latin == new_has_latin:
                            question["review_required"] = True
                    question["_option_started"] = True
                    prefix_fragments = sorted(pending_option_prefix.pop(option_id, []), key=lambda item: item[1].y0)
                    if prefix_fragments:
                        option_record = next((item for item in question["options"] if item["id"] == option_id), None)
                        if option_record is not None:
                            prefix_text = " ".join(fragment for fragment, _ in prefix_fragments)
                            option_record["text"] = " ".join(part for part in (prefix_text, option_record["text"]) if part)
                            option_record["original_text"] = option_record["text"]
                            option_record.setdefault("source", {}).setdefault("content_bboxes", []).extend(list(fragment_bbox) for _, fragment_bbox in prefix_fragments)
                    for fragment, fragment_bbox in pending_option_math.pop(option_id, []):
                        question.setdefault("_pending_fraction_numerators", {}).setdefault(option_id, []).append((fragment, fragment_bbox))
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
                        option_id = _option_for_position(question["_option_anchors"], line_bbox)
                    else:
                        option_id = question["options"][-1]["id"]
                    option = next((item for item in question["options"] if item["id"] == option_id), None)
                    if option is not None:
                        numerators = question.get("_pending_fraction_numerators", {}).get(option_id, [])
                        fraction = None
                        if text.strip().isdigit() and line_bbox is not None:
                            for numerator, numerator_bbox in numerators:
                                numerator_rect = fitz.Rect(numerator_bbox)
                                for rule_values in page.get("fraction_rules", []):
                                    rule = fitz.Rect(rule_values)
                                    if numerator_rect.y1 <= rule.y0 <= line_bbox.y1 and rule.x1 >= numerator_rect.x0 and rule.x0 <= line_bbox.x1:
                                        fraction = f"{numerator}/{text.strip()}"
                                        break
                                denominator_center = (line_bbox.x0 + line_bbox.x1) / 2
                                numerator_center = (numerator_rect.x0 + numerator_rect.x1) / 2
                                vertical_gap = line_bbox.y0 - numerator_rect.y1
                                aligned_stack = abs(denominator_center - numerator_center) <= 8 and 0 <= vertical_gap <= 20
                                if aligned_stack:
                                    fraction = f"{numerator}/{text.strip()}"
                                if fraction:
                                    break
                        addition = fraction or text
                        option["text"] = " ".join(part for part in (option["text"], addition) if part)
                        if fraction:
                            question["_pending_fraction_numerators"][option_id].remove(next(item for item in numerators if item[0] == fraction.split("/", 1)[0]))
                        if line_bbox is not None:
                            option.setdefault("source", {}).setdefault("content_bboxes", []).append(list(line_bbox))
                        option["original_text"] = option["text"]
                        option["review_required"] = not bool(option["text"].strip())
                    continue
            question["_lines"].append(text)

        if question is not None and int(question["question_number"]) == 50:
            flush_question()

    flush_question()

    if current_section["questions"]:
        sections.append(current_section)

    return sections


def _crop_option_source(option, question, page_data, source_document, media_dir):
    bbox = option.get("source", {}).get("bbox")
    if source_document is None or not media_dir or not bbox:
        return None
    page_number = option.get("source", {}).get("page")
    if not page_number:
        return None
    marker = fitz.Rect(bbox)
    page_width = page_data.get("width", 0)
    page_height = page_data.get("height", 0)
    same_row = [
        fitz.Rect(other["source"]["bbox"])
        for other in question["options"]
        if other is not option and other.get("source", {}).get("bbox")
        and abs(fitz.Rect(other["source"]["bbox"]).y0 - marker.y0) <= 10
    ]
    right_candidates = [rect.x0 for rect in same_row if rect.x0 > marker.x0]
    column_right = page_width / 2 if marker.x0 < page_width / 2 else page_width - 24
    x0 = marker.x1 + 1
    x1 = min(right_candidates, default=column_right) - 2
    later_rows = [
        fitz.Rect(other["source"]["bbox"]).y0
        for other in question["options"]
        if other is not option and other.get("source", {}).get("bbox")
        and fitz.Rect(other["source"]["bbox"]).y0 > marker.y0 + 10
        and abs(fitz.Rect(other["source"]["bbox"]).x0 - marker.x0) < 35
    ]
    next_questions = [
        float(line[0]) for line in page_data.get("lines", [])
        if (match := QUESTION_RE.match(line[2]))
        and int(match.group(1)) > int(question["question_number"])
        and line[0] > marker.y0
        and abs(line[1] - question.get("source", {}).get("bbox", [marker.x0])[0]) < page_width * 0.18
    ]
    y1 = min(later_rows + next_questions + [marker.y0 + 42, page_height - 12])
    clip = fitz.Rect(x0, marker.y0 - 2, x1, y1 - 2)
    if clip.width < 18 or clip.height < 12:
        return None
    try:
        source_page = source_document[page_number - 1]
        clip &= source_page.rect
        pixmap = source_page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip, alpha=False)
        image = Image.open(BytesIO(pixmap.tobytes("png"))).convert("L")
        dark_pixels = sum(pixel < 220 for pixel in image.get_flattened_data())
        if dark_pixels / max(1, image.width * image.height) < 0.012:
            return None
        filename = f"p{page_number}_q{question['question_number']}_option_{option['id']}.png"
        destination = media_dir / filename
        if destination.exists():
            return None
        destination.write_bytes(pixmap.tobytes("png"))
        return {
            "asset_id": Path(filename).stem,
            "filename": filename,
            "type": "option_crop",
            "source_page": page_number,
            "bbox": list(clip),
            "content": None,
        }
    except Exception:
        logger.exception("Could not crop unreadable option source: q=%s option=%s", question.get("question_number"), option.get("id"))
        return None


def attach_media(sections, media, pages, source_document=None, media_dir=None):
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
                reason = "Question position could not be mapped to PDF coordinates, so media association was skipped."
                question["review_reasons"] = list(dict.fromkeys(question.get("review_reasons", []) + [reason]))
                question["review_required"] = True
                continue

            start_y = source_bbox[1] if source_bbox else min(item[0] for item in start_lines)
            start_x = source_bbox[0] if source_bbox else min(item[1] for item in start_lines)

            next_positions = []

            for y, x, text, bbox, *_ in page["lines"]:
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
                    if not any(item.get("asset_id") == asset.get("asset_id") for item in question["media"]):
                        question["media"].append({**asset, "source_page": page_number})

            # Only promote a vector crop to an option when it is physically adjacent
            # to that option's own text box. Each asset can belong to at most one choice.
            assigned_assets = set()
            for option in question["options"]:
                option_bbox = option.get("source", {}).get("bbox")
                if not option_bbox:
                    continue
                option_rect = fitz.Rect(option_bbox)
                for asset in question["media"]:
                    asset_bbox = asset.get("bbox")
                    if asset.get("type") != "diagram" or not asset_bbox or asset.get("asset_id") in assigned_assets:
                        continue
                    asset_rect = fitz.Rect(asset_bbox)
                    horizontal_gap = max(option_rect.x0 - asset_rect.x1, asset_rect.x0 - option_rect.x1, 0)
                    vertical_gap = max(option_rect.y0 - asset_rect.y1, asset_rect.y0 - option_rect.y1, 0)
                    overlaps_inline = option_rect.y0 <= asset_rect.y1 and asset_rect.y0 <= option_rect.y1
                    if horizontal_gap <= 100 and vertical_gap <= 120 and (overlaps_inline or vertical_gap > 0):
                        option["media"].append(dict(asset))
                        option["review_required"] = False
                        assigned_assets.add(asset.get("asset_id"))
                        break
            if assigned_assets:
                question["media"] = [asset for asset in question["media"] if asset.get("asset_id") not in assigned_assets]
                if all(option["text"].strip() or option["media"] for option in question["options"]):
                    question["review_reasons"] = [
                        reason for reason in question.get("review_reasons", [])
                        if reason != "One or more options have neither readable text nor associated media."
                    ]
                    question["review_required"] = bool(question["review_reasons"])

            for option in question["options"]:
                if option.get("text", "").strip() or option.get("media"):
                    continue
                crop = _crop_option_source(option, question, page, source_document, media_dir)
                if crop:
                    option["media"].append(crop)
                    option["review_required"] = True
                    reason = f"Option {option['id']} has a visual source crop, but its mathematical text could not be extracted reliably."
                    question["review_reasons"] = list(dict.fromkeys(question.get("review_reasons", []) + [reason]))
            if all(option.get("text", "").strip() or option.get("media") for option in question["options"]):
                question["review_reasons"] = [
                    reason for reason in question.get("review_reasons", [])
                    if reason != "One or more options have neither readable text nor associated media."
                ]
                question["review_required"] = bool(question["review_reasons"]) or any(option.get("review_required") for option in question["options"])

            if len({option["id"] for option in question["options"]}) < 4 and question.get("_option_started"):
                reason = "One or more numbered choices were not recovered from the source text."
                question["review_reasons"] = list(dict.fromkeys(question.get("review_reasons", []) + [reason]))
                question["review_required"] = True


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
                "native_text": page.get("native_text", ""),
                "reconstructed_text": page.get("source_text", page.get("text", "")),
                "ocr_text": page.get("ocr_text", ""),
                "ocr_used": page.get("ocr_used", False),
                "needs_review": page.get("needs_review", False),
                "warnings": page.get("ocr_warnings", []),
                "spans": page.get("spans", []),
                "span_lines": page.get("span_lines", []),
                "fonts": page.get("fonts", []),
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

        with fitz.open(source_path) as source_document:
            attach_media(
                sections,
                document_data["media"],
                document_data["pages"],
                source_document=source_document,
                media_dir=root / "media",
            )
        for section in sections:
            for parsed_question in section["questions"]:
                # Keep source coordinates in output for audit/debugging.
                parsed_question.pop("_option_started", None)
                parsed_question.pop("_option_anchors", None)
                parsed_question.pop("_page_needs_review", None)
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
                    parsed_question["review_reasons"] = list(dict.fromkeys(parsed_question.get("review_reasons", []) + [f"Answer for question {number} could not be matched unambiguously."]))
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
                parsed_question["review_reasons"] = list(dict.fromkeys(parsed_question.get("review_reasons", []) + ["No unambiguous answer-key entry was found for this question."]))
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

        validated_result = DocumentResult.model_validate(result)
        referenced_media = set()
        for section in validated_result.sections:
            for parsed_question in section.questions:
                referenced_media.update(asset.filename for asset in parsed_question.media)
                for option in parsed_question.options:
                    referenced_media.update(asset.filename for asset in option.media)
        missing_media = sorted(filename for filename in referenced_media if not (root / "media" / filename).is_file())
        if missing_media:
            raise ValueError(f"Generated media references are missing files: {', '.join(missing_media)}")
        result = validated_result.model_dump(mode="json")

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
