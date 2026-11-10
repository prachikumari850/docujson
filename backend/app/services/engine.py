import json
import hashlib
import logging
import os
import re
from collections import Counter
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
from app.services.vision import verify_math_image

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
    language_neutral_math = []

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
        elif re.search(r"[\u2200-\u22ff\u0370-\u03ff^_=+*/√∫∑∏]", line) and re.fullmatch(r"[\d\s\u2200-\u22ff\u0370-\u03ff^_=+*/√∫∑∏().,;:|\[\]{}−×÷±]+", line):
            # Math-only layout lines (e.g. stacked integral limits) belong with
            # the bilingual stem. Dropping them here made English/Hindi fields
            # lose formulas that PyMuPDF correctly extracted as separate lines.
            language_neutral_math.append(line)

    if language_neutral_math:
        if english:
            english = language_neutral_math + english
        if hindi:
            hindi = language_neutral_math + hindi

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
    # Some embedded fonts cause the normal-sized printed (1)/(2) option label
    # to be decoded as superscript glyphs. Normalize only at the start of a
    # candidate line; superscripts inside the formula remain untouched.
    line = re.sub(
        r"^\s*⁽([¹²³⁴])⁾",
        lambda match: "(" + match.group(1).translate(str.maketrans("¹²³⁴", "1234")) + ")",
        line,
    )
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


def _spatial_reflow_fragments(fragments: list[dict]) -> str:
    """Reorder expression parts by x within geometric rows, not parser arrival order."""
    usable = []
    for fragment in fragments:
        text = str(fragment.get("text", "")).strip()
        bbox = fragment.get("bbox")
        if text and bbox and len(bbox) == 4:
            usable.append((fitz.Rect(bbox), text))
    if not usable:
        return ""
    usable.sort(key=lambda item: (item[0].y0, item[0].x0))
    rows: list[list[tuple[fitz.Rect, str]]] = []
    for item in usable:
        rect, _ = item
        candidates = [
            row for row in rows
            if min(row[-1][0].y1, rect.y1) - max(row[-1][0].y0, rect.y0) > 0
            or abs(row[-1][0].y0 - rect.y0) <= 5.5
        ]
        if candidates:
            row = min(candidates, key=lambda candidate: abs(candidate[0][0].y0 - rect.y0))
            row.append(item)
        else:
            rows.append([item])
    return "\n".join(
        " ".join(text for _, text in sorted(row, key=lambda item: item[0].x0))
        for row in rows
    ).strip()


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
        "pixel_width": width,
        "pixel_height": height,
        "extraction_method": media_type,
        "confidence": None,
        "content": None,
    }


def _text_quality(text: str) -> float:
    if not text.strip():
        return 0.0
    suspicious = len(re.findall(r"[\ufffd\uf000-\uf8ff]", text))
    useful = len(re.findall(r"[A-Za-z\u0900-\u097f0-9\u00a0-\u024f\u0370-\u03ff\u2000-\u2bff]", text))
    controls = len(re.findall(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", text))
    return useful / max(1, len(text)) - min(0.8, (suspicious + controls) / max(1, len(text)))


def _has_encoding_artifacts(text: str) -> bool:
    """Detect likely mojibake without mutating the original extracted evidence."""
    return bool(re.search(r"(?:Ã[\u0080-\u00ff]|Â[\u0080-\u00ff]|â(?:€|‚|ƒ|ˆ|…|—|™|[\u0080-\u00ff])|áµ[\u0080-\u00ff]|ðŸ|\ufffd|[\uf000-\uf8ff])", text))


def _has_displaced_short_option_content(option: dict) -> bool:
    """Flag short choices whose recorded glyphs sit above/below the label baseline."""
    text = option.get("text", "").strip()
    source = option.get("source", {})
    marker_values = source.get("bbox")
    if len(text) > 2 or not marker_values:
        return False
    marker = fitz.Rect(marker_values)
    for values in source.get("content_bboxes", []):
        if len(values) != 4:
            continue
        rect = fitz.Rect(values)
        if rect.x0 >= marker.x0 - 2 and rect.x1 <= marker.x1 + 2:
            continue
        if abs((rect.y0 + rect.y1) / 2 - (marker.y0 + marker.y1) / 2) > max(3.0, marker.height * 0.28):
            return True
    return False


def _has_suspicious_math_layout(text: str) -> bool:
    """Identify visibly fragmented short formula rows without rewriting them."""
    if any(mark in text for mark in ("₍", "₎", "\ufffd")):
        return True
    rows = [row.strip() for row in text.splitlines() if row.strip()]
    if len(rows) > 1 and any(
        len(row) <= 2 and re.search(r"[0-9πθ√∫∑∏=+−\-*/()\[\]{}]", row)
        for row in rows
    ):
        return True
    if any(token in text for token in ("cos−¹", "sin−¹", "tan−¹", "cos-¹", "sin-¹", "tan-¹")):
        if text.count("(") != text.count(")"):
            return True
    rows = [row.strip() for row in text.splitlines() if row.strip()]
    unit_axes = re.findall(r"(?<![A-Za-z])[ijk]\u0302", text)
    if any(re.fullmatch(r"[ijk]\u0302", row) for row in rows):
        return True
    if len(rows) > 1 and any(
        sum(len(re.findall(rf"(?<![A-Za-z]){axis}\u0302", row)) for row in rows) > 1
        for axis in "ijk"
    ):
        return True
    coefficient_count = len(re.findall(r"(?:\d+\s*/\s*\d+|\b\d+\b)", text))
    if coefficient_count >= 3 and len(unit_axes) < 3 and unit_axes:
        return True
    return False


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
    character_records = [
        (span, char)
        for span in ordered
        for char in span.get("chars", [])
        if char.get("c", "").strip() and len(char.get("origin", [])) > 1
    ]
    span_sizes = [float(span.get("size", 0) or 0) for span, _ in character_records if float(span.get("size", 0) or 0) > 0]
    reference_size = sorted(span_sizes)[len(span_sizes) // 2] if span_sizes else 0
    baseline_records = [
        char.get("origin", [0, 0])[1]
        for span, char in character_records
        if reference_size == 0 or float(span.get("size", 0) or 0) >= reference_size * 0.84
    ]
    reference_baseline = sorted(baseline_records)[len(baseline_records) // 2] if baseline_records else None
    reference_heights = [
        fitz.Rect(char.get("bbox", span.get("bbox", [0, 0, 0, 0]))).height
        for span, char in character_records
        if reference_size == 0 or float(span.get("size", 0) or 0) >= reference_size * 0.84
    ]
    reference_height = sorted(reference_heights)[len(reference_heights) // 2] if reference_heights else None
    pieces: list[str] = []
    rendered_span_values = {}
    previous = None
    for span in ordered:
        value = repair_pdf_mojibake(_render_span_scripts(span, reference_baseline, reference_height))
        rendered_span_values[id(span)] = value
        if not value:
            continue
        if previous is not None and pieces:
            gap = float(span.get("bbox", [0])[0]) - float(previous.get("bbox", [0, 0, 0, 0])[2])
            size = max(float(span.get("size", 0) or 0), float(previous.get("size", 0) or 0))
            if gap > max(1.5, size * 0.18) and not pieces[-1].endswith((" ", "\t")) and not value.startswith((" ", "\t")):
                pieces.append(" ")
        pieces.append(value)
        previous = span
    joined = "".join(pieces).strip()
    joined = re.sub(r"([A-Za-z0-9])\s+([\u2070-\u209f\u1d2c-\u1d7f])", r"\1\2", joined)
    # Arrow text is not sufficient evidence of vector notation: e.g. ``A → B``
    # is a relation, while a separately drawn arrow above A is a vector mark.
    # Only combine an arrow glyph when its character box geometrically overlaps
    # a single letter and sits above that letter. Otherwise preserve the arrow.
    arrow_chars = []
    base_chars = []
    for span in ordered:
        for char in span.get("chars", []):
            value = char.get("c", "")
            if value in ("\u2192", "\u20d7"):
                arrow_chars.append((span, char, fitz.Rect(char.get("bbox", span.get("bbox", (0, 0, 0, 0))))))
            elif value.strip() and len(value.strip()) == 1 and value.strip().isalpha():
                base_chars.append((span, char, fitz.Rect(char.get("bbox", span.get("bbox", (0, 0, 0, 0))))))

    insertions: dict[int, list[tuple[int, str]]] = {}
    removed_arrows = set()
    for arrow_span, arrow_char, arrow_rect in arrow_chars:
        candidates = []
        for base_span, base_char, base_rect in base_chars:
            if base_char is arrow_char:
                continue
            overlap = min(arrow_rect.x1, base_rect.x1) - max(arrow_rect.x0, base_rect.x0)
            if overlap <= 0 or arrow_rect.y1 > base_rect.y0 + 1.0:
                continue
            if base_rect.height <= 0 or overlap / base_rect.width < 0.35:
                continue
            candidates.append((abs((arrow_rect.x0 + arrow_rect.x1 - base_rect.x0 - base_rect.x1) / 2), base_span, base_char))
        if not candidates:
            continue
        _, base_span, base_char = min(candidates, key=lambda candidate: candidate[0])
        offset = _character_text_offset([base_span], base_char)
        if offset < 0:
            continue
        insertions.setdefault(id(base_span), []).append((offset + len(base_char.get("c", "")), "\u20d7"))
        removed_arrows.add((id(arrow_span), id(arrow_char)))

    if not insertions and not removed_arrows:
        return joined

    pieces = []
    previous = None
    for span in ordered:
        value = rendered_span_values.get(id(span), repair_pdf_mojibake(_render_span_scripts(span, reference_baseline, reference_height)))
        if not value:
            continue
        chars = span.get("chars", [])
        arrow_values = {
            char.get("c", "") for char in chars
            if (id(span), id(char)) in removed_arrows
        }
        if arrow_values:
            for arrow in arrow_values:
                value = value.replace(arrow, "", 1)
        offsets = insertions.get(id(span), [])
        for offset, mark in sorted(offsets, reverse=True):
            value = value[:offset] + mark + value[offset:]
        if not value:
            continue
        if previous is not None and pieces:
            gap = float(span.get("bbox", [0])[0]) - float(previous.get("bbox", [0, 0, 0, 0])[2])
            size = max(float(span.get("size", 0) or 0), float(previous.get("size", 0) or 0))
            if gap > max(1.5, size * 0.18) and not pieces[-1].endswith((" ", "\t")) and not value.startswith((" ", "\t")):
                pieces.append(" ")
        pieces.append(value)
        previous = span
    return re.sub(r"([A-Za-z0-9])\s+([\u2070-\u209f\u1d2c-\u1d7f])", r"\1\2", "".join(pieces).strip())


def _ordered_layout_lines(lines, page_width: float):
    """Order full-width separators and independent columns without a page-wide y sort."""
    if not lines:
        return [], None

    def order_rows(items):
        # Keep native visual order based on the span rectangle. The separate
        # baseline value is used by the parser for ownership only; sorting the
        # rendered page by baselines reorders stacked bilingual option cells.
        return sorted(items, key=lambda item: (item[3].y0, item[3].x0))

    full, left, right = [], [], []
    for item in lines:
        rect = item[3]
        if rect.width >= page_width * 0.68 or (rect.x0 < page_width * 0.12 and rect.x1 > page_width * 0.88):
            full.append(item)
        elif (rect.x0 + rect.x1) / 2 < page_width / 2:
            left.append(item)
        else:
            right.append(item)
    full = order_rows(full)
    left = order_rows(left)
    right = order_rows(right)
    if not left or not right:
        ordered = order_rows(lines)
        return ordered, None

    # A full-width heading/paragraph separates reading-order bands. Within each
    # band, read down the left column and then down the right column.
    ordered = []
    previous_y = float("-inf")
    for separator in full:
        separator_y = separator[3].y0
        ordered.extend(item for item in left if previous_y < item[3].y0 < separator_y)
        ordered.extend(item for item in right if previous_y < item[3].y0 < separator_y)
        ordered.append(separator)
        previous_y = separator_y
    ordered.extend(item for item in left if item[3].y0 > previous_y)
    ordered.extend(item for item in right if item[3].y0 > previous_y)
    bounds = {
        "left": [min(item[3].x0 for item in left), max(item[3].x1 for item in left)],
        "right": [min(item[3].x0 for item in right), max(item[3].x1 for item in right)],
    }
    return ordered, bounds


def _cluster_drawing_rectangles(drawings, page_rect: fitz.Rect) -> list[fitz.Rect]:
    """Group adjacent PDF vector primitives into diagram regions before filtering."""
    rects = []
    for drawing in drawings:
        try:
            rect = fitz.Rect(drawing["rect"]) & page_rect
        except (KeyError, TypeError, ValueError):
            continue
        if rect.is_empty or rect.width < 0.8 and rect.height < 0.8:
            continue
        rects.append(rect)
    if not rects:
        return []

    parent = list(range(len(rects)))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left_index, right_index):
        left_root, right_root = find(left_index), find(right_index)
        if left_root != right_root:
            parent[right_root] = left_root

    # Small vector pieces commonly form one graph or diagram. Join only close
    # geometry, and reject unions that would swallow a substantial page region.
    max_union_area = page_rect.get_area() * 0.32
    for left_index, left_rect in enumerate(rects):
        for right_index in range(left_index + 1, len(rects)):
            right_rect = rects[right_index]
            x_gap = max(left_rect.x0 - right_rect.x1, right_rect.x0 - left_rect.x1, 0)
            y_gap = max(left_rect.y0 - right_rect.y1, right_rect.y0 - left_rect.y1, 0)
            if x_gap > 9 or y_gap > 9:
                continue
            if (left_rect | right_rect).get_area() <= max_union_area:
                union(left_index, right_index)

    groups: dict[int, fitz.Rect] = {}
    for index, rect in enumerate(rects):
        root = find(index)
        groups[root] = rect if root not in groups else groups[root] | rect

    regions = []
    page_area = max(1, page_rect.get_area())
    for rect in groups.values():
        if rect.width < 45 or rect.height < 35:
            continue
        if rect.y0 < page_rect.height * 0.10 or rect.y1 > page_rect.height * 0.94:
            continue
        if rect.get_area() < page_area * 0.0015 or rect.get_area() > page_area * 0.24:
            continue
        if rect.width > page_rect.width * 0.82 or rect.height > page_rect.height * 0.62:
            continue
        if rect.width / max(rect.height, 1) > 7.5 or rect.height / max(rect.width, 1) > 7.5:
            continue
        regions.append(rect)
    return sorted(regions, key=lambda rect: (rect.y0, rect.x0))


def _layout_column(bbox, page_width: float) -> str:
    rect = fitz.Rect(bbox)
    if rect.width >= page_width * 0.68:
        return "full"
    return "left" if (rect.x0 + rect.x1) / 2 < page_width / 2 else "right"


def _render_span_scripts(span: dict, reference_baseline: float | None = None, reference_height: float | None = None) -> str:
    chars = span.get("chars", [])
    if not chars:
        return span.get("text", "")
    valid_origins = [char.get("origin", [0, 0])[1] for char in chars if char.get("c", "").strip() and len(char.get("origin", [])) > 1]
    if reference_baseline is None and not valid_origins:
        return span.get("text", "")
    baseline = reference_baseline if reference_baseline is not None else sorted(valid_origins)[len(valid_origins) // 2]
    heights = [fitz.Rect(item.get("bbox", span.get("bbox", [0, 0, 0, 0]))).height for item in chars if item.get("c", "").strip()]
    span_height = reference_height or (sorted(heights)[len(heights) // 2] if heights else fitz.Rect(span.get("bbox", [0, 0, 0, 0])).height)
    output = []
    for char in chars:
        value = char.get("c", "")
        origin = char.get("origin", [0, baseline])
        delta = baseline - origin[1] if len(origin) > 1 else 0
        bbox = fitz.Rect(char.get("bbox", span.get("bbox", [0, 0, 0, 0])))
        if delta >= max(1.6, span_height * 0.12):
            value = value.translate(_SUPERSCRIPTS)
            if value == "/":
                value = "\u2044"
        elif delta <= -max(1.6, span_height * 0.12):
            value = value.translate(_SUBSCRIPTS)
        output.append(value)
    return "".join(output)


_SUPERSCRIPTS = str.maketrans({"0": "\u2070", "1": "\u00b9", "2": "\u00b2", "3": "\u00b3", "4": "\u2074", "5": "\u2075", "6": "\u2076", "7": "\u2077", "8": "\u2078", "9": "\u2079", "+": "\u207a", "-": "\u207b", "=": "\u207c", "(": "\u207d", ")": "\u207e", "i": "\u2071", "n": "\u207f", "t": "\u1d57", "x": "\u02e3", "y": "\u02b8", "a": "\u1d43", "b": "\u1d47", "e": "\u1d49"})
_SUBSCRIPTS = str.maketrans("0123456789+-=()", "\u2080\u2081\u2082\u2083\u2084\u2085\u2086\u2087\u2088\u2089\u208a\u208b\u208c\u208d\u208e")


def _attach_detached_scripts(lines):
    """Attach only geometrically raised/lowered, compact glyph rows to a nearby baseline."""
    result = list(lines)
    consumed = set()
    for index, item in enumerate(result):
        if index in consumed:
            continue
        y, x, text, rect, spans = item
        token = text.strip()
        if not token or len(token) > 2 or not all(char in "0123456789+-=()tinxy" for char in token):
            continue
        char_records = [char for span in spans for char in span.get("chars", []) if char.get("c", "").strip()]
        if not char_records:
            continue
        origin_y = char_records[0].get("origin", [0, rect.y1])[1]
        char_height = max((fitz.Rect(char["bbox"]).height for char in char_records), default=rect.height)
        candidates = []
        for target_index, target in enumerate(result):
            if target_index == index or target_index in consumed:
                continue
            ty, tx, target_text, target_rect, target_spans = target
            if target_rect.height < char_height * 1.15 or abs((target_rect.x0 + target_rect.x1) / 2 - (rect.x0 + rect.x1) / 2) > max(80, rect.width * .55):
                continue
            target_chars = [char for span in target_spans for char in span.get("chars", []) if char.get("c", "").strip()]
            if not target_chars:
                continue
            baseline = sum(char.get("origin", [0, 0])[1] for char in target_chars) / len(target_chars)
            delta = baseline - origin_y
            if not 2.5 <= abs(delta) <= max(12, target_rect.height * .72):
                continue
            preceding = [char for char in target_chars if fitz.Rect(char["bbox"]).x1 <= rect.x0 + 2]
            if not preceding:
                continue
            base_char = max(preceding, key=lambda char: fitz.Rect(char["bbox"]).x1)
            gap = rect.x0 - fitz.Rect(base_char["bbox"]).x1
            if not -2 <= gap <= max(5, char_height * .65):
                continue
            candidates.append((abs(delta), gap, target_index, base_char, delta))
        if not candidates:
            continue
        _, _, target_index, base_char, delta = min(candidates)
        target = result[target_index]
        target_text = target[2]
        base_char_text = base_char.get("c", "")
        char_position = _character_text_offset(target[4], base_char)
        if char_position < 0:
            continue
        mapping = _SUPERSCRIPTS if delta > 0 else _SUBSCRIPTS
        script = token.translate(mapping)
        if script == token and token.isdigit():
            continue
        updated_text = target_text[:char_position + len(base_char_text)] + script + target_text[char_position + len(base_char_text):]
        updated_text = re.sub(r"([A-Za-z0-9])\s+([\u2070-\u209f\u1d2c-\u1d7f])", r"\1\2", updated_text)
        result[target_index] = (target[0], target[1], updated_text, target[3] | rect, target[4] + spans)
        consumed.add(index)
    return [item for index, item in enumerate(result) if index not in consumed]


def _character_text_offset(spans, wanted):
    """Map a rawdict character's geometric identity back to the joined line string."""
    ordered = sorted(spans, key=lambda span: (span.get("bbox", [0, 0])[0], span.get("bbox", [0, 0])[1]))
    pieces = []
    previous = None
    offset = 0
    for span in ordered:
        chars = span.get("chars", [])
        value = "".join(char.get("c", "") for char in chars) if chars else span.get("text", "")
        if not value:
            continue
        if previous is not None and pieces:
            gap = float(span.get("bbox", [0])[0]) - float(previous.get("bbox", [0, 0, 0, 0])[2])
            size = max(float(span.get("size", 0) or 0), float(previous.get("size", 0) or 0))
            if gap > max(1.5, size * 0.18) and not pieces[-1].endswith((" ", "\t")) and not value.startswith((" ", "\t")):
                pieces.append(" ")
                offset += 1
        for char_index, char in enumerate(chars):
            if char is wanted or (char.get("c") == wanted.get("c") and char.get("bbox") == wanted.get("bbox")):
                return offset + char_index
        pieces.append(value)
        offset += len(value)
        previous = span
    return -1


def _associate_detached_vector_marks(lines):
    """Join detached over-arrow/hat glyph lines to a base only on glyph overlap.

    Type3 fonts in the SRG source encode vector arrows and unit-vector hats as
    separate text objects. Their bounding boxes overlap the variable glyph
    above it, but the PDF line extractor places each mark on its own line.
    Keep all span evidence and record every geometry-based association.
    """
    marks = []
    bases = []
    for line_index, line in enumerate(lines):
        mark_text = line[2].strip()
        if mark_text not in {"→", "ˆ", "^", "̂", "⌃"}:
            continue
        mark_chars = [
            char
            for span in line[4]
            for char in span.get("chars", [])
            if char.get("c", "").strip() in {"→", "ˆ", "^", "̂", "⌃"}
        ]
        if not mark_chars:
            continue
        marks.append((line_index, mark_text, fitz.Rect(mark_chars[0].get("bbox", line[3])), mark_chars[0]))

    for line_index, line in enumerate(lines):
        for span in line[4]:
            for char in span.get("chars", []):
                value = char.get("c", "").strip()
                if len(value) == 1 and value.isalpha():
                    bases.append((line_index, value, fitz.Rect(char.get("bbox", span.get("bbox", line[3]))), char))

    consumed = set()
    claimed_bases = set()
    associations = []
    updated = list(lines)
    insertions: dict[int, list[tuple[int, str]]] = {}
    mark_rects: dict[int, fitz.Rect] = {}
    for mark_index, mark_text, mark_rect, mark_char in marks:
        candidates = []
        for base_index, base_char_value, base_rect, base_char in bases:
            if base_index == mark_index or (base_index, id(base_char)) in claimed_bases:
                continue
            overlap_x = min(mark_rect.x1, base_rect.x1) - max(mark_rect.x0, base_rect.x0)
            if overlap_x <= 0 or overlap_x / max(0.1, base_rect.width) < 0.45:
                continue
            horizontal_centres = abs((mark_rect.x0 + mark_rect.x1 - base_rect.x0 - base_rect.x1) / 2)
            if horizontal_centres > max(2.5, base_rect.width * 0.55):
                continue
            vertical_centres = (base_rect.y0 + base_rect.y1 - mark_rect.y0 - mark_rect.y1) / 2
            if not 1.0 <= vertical_centres <= max(15.0, base_rect.height * 0.95):
                continue
            candidates.append((horizontal_centres + vertical_centres * 0.12, base_index, base_char_value, base_rect, base_char))
        if not candidates:
            continue
        _, base_index, base_value, base_rect, base_char = min(candidates, key=lambda item: item[0])
        mark = "\u20d7" if mark_text == "→" else "\u0302"
        target = lines[base_index]
        offset = _character_text_offset(target[4], base_char)
        if offset < 0:
            continue
        insertion = offset + len(base_char.get("c", ""))
        insertions.setdefault(base_index, []).append((insertion, mark))
        mark_rects[base_index] = mark_rect if base_index not in mark_rects else mark_rects[base_index] | mark_rect
        consumed.add(mark_index)
        claimed_bases.add((base_index, id(base_char)))
        associations.append({
            "mark": mark_text,
            "normalized_mark": mark,
            "base_character": base_value,
            "mark_bbox": list(mark_rect),
            "base_bbox": list(base_rect),
            "source_line_index": mark_index,
            "target_line_index": base_index,
            "method": "character_bbox_overlap_and_vertical_offset",
        })
    for line_index, line_insertions in insertions.items():
        source = lines[line_index]
        text = source[2]
        for insertion, mark in sorted(line_insertions, reverse=True):
            text = text[:insertion] + mark + text[insertion:]
        # Keep the original line box stable; the over-arrow evidence remains
        # separately recorded and must not shift line reading order or owners.
        updated[line_index] = (source[0], source[1], text, source[3], source[4])
    return [line for index, line in enumerate(updated) if index not in consumed], associations


def repair_pdf_mojibake(text: str) -> str:
    """Repair verifiable UTF-8-as-Windows-1252 layers; preserve originals elsewhere."""
    marker_pattern = "(?:" + re.escape(chr(0xC3)) + ".|" + re.escape(chr(0xC2)) + ".|" + re.escape(chr(0xE2)) + ".|" + re.escape(chr(0xE0) + chr(0xA4)) + "|" + re.escape(chr(0xE0) + chr(0xA5)) + "|" + re.escape(chr(0xCE)) + ".|" + re.escape(chr(0xCF)) + ".)"
    markers = re.compile(marker_pattern)
    if not text or not markers.search(text):
        return text
    current = text
    for _ in range(3):
        if not markers.search(current):
            break
        try:
            candidate = current.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        if len(markers.findall(candidate)) >= len(markers.findall(current)):
            break
        current = candidate
    return current

def _reconstruct_stacked_fractions(lines, fraction_rules=()):
    """Join compact numerator/denominator text only when page geometry aligns them."""
    consumed = set()
    reconstructed = []
    for index, line in enumerate(lines):
        if index in consumed:
            continue
        y, x, text, bbox, spans = line
        token = text.strip()
        math_letters = r"A-Za-z0-9\u00b9\u00b2\u00b3\u0370-\u03ff\u2070-\u209f\u1d2c-\u1d7f\u221a\u221b"
        if not re.fullmatch(f"[{math_letters}]+", token) or not re.search(r"\d|[\u2070-\u2079\u00b9\u00b2\u00b3]", token):
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
            if not re.fullmatch(f"[{math_letters}]+", denominator):
                continue
            x_overlap = min(bbox.x1, next_bbox.x1) - max(bbox.x0, next_bbox.x0)
            if x_overlap >= 0 and abs((bbox.x0 + bbox.x1) / 2 - (next_bbox.x0 + next_bbox.x1) / 2) <= 9 and 4 <= gap <= 28:
                for rule_values in fraction_rules:
                    rule = fitz.Rect(rule_values)
                    overlap_num = min(rule.x1, bbox.x1) - max(rule.x0, bbox.x0)
                    overlap_den = min(rule.x1, next_bbox.x1) - max(rule.x0, next_bbox.x0)
                    if not (
                        rule.width >= 4
                        and rule.height <= 1.5
                        and rule.y0 >= bbox.y1 - 2
                        and rule.y1 <= next_bbox.y0 + 2
                        and overlap_num >= min(3.0, bbox.width * 0.7)
                        and overlap_den >= min(3.0, next_bbox.width * 0.7)
                    ):
                        continue
                    intervening = any(
                        between_index not in consumed
                        and bbox.y1 <= lines[between_index][3].y0 < next_bbox.y0
                        and min(rule.x1, lines[between_index][3].x1) > max(rule.x0, lines[between_index][3].x0)
                        for between_index in range(index + 1, next_index)
                    )
                    if not intervening:
                        candidates.append((gap, next_index, denominator, next_bbox, next_spans))
                        break
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
    media_hashes = {}
    media_duplicates = []

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

            page_width = page.rect.width
            ordered_lines, column_bounds = _ordered_layout_lines(text_lines, page_width)
            native_ordered_lines = list(ordered_lines)
            column_texts = None
            if column_bounds:
                column_texts = [
                    [item[2] for item in text_lines if (item[3].x0 + item[3].x1) / 2 < page_width / 2 and item[3].width < page_width * 0.68],
                    [item[2] for item in text_lines if (item[3].x0 + item[3].x1) / 2 >= page_width / 2 and item[3].width < page_width * 0.68],
                ]
            fraction_rules = [list(drawing["rect"]) for drawing in drawings if fitz.Rect(drawing["rect"]).height <= 1.5 and fitz.Rect(drawing["rect"]).width >= 4]
            ordered_lines = _reconstruct_stacked_fractions(ordered_lines, fraction_rules)
            ordered_lines = _attach_detached_scripts(ordered_lines)
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
                    ordered_lines, column_bounds = _ordered_layout_lines(ocr_lines, page_width)
                    column_texts = None
                    if column_bounds:
                        column_texts = [
                            [item[2] for item in ocr_lines if (item[3].x0 + item[3].x1) / 2 < page_width / 2 and item[3].width < page_width * 0.68],
                            [item[2] for item in ocr_lines if (item[3].x0 + item[3].x1) / 2 >= page_width / 2 and item[3].width < page_width * 0.68],
                        ]
                    page_text = "\n".join(item[2] for item in ordered_lines)
                    ocr_used = bool(page_text)
                    ocr_warnings.append("OCR text replaced native page text because native extraction quality was poor; both versions remain in debug data.")

            ordered_lines, vector_mark_associations = _associate_detached_vector_marks(ordered_lines)
            page_text = "\n".join(item[2] for item in ordered_lines)

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
                    "vector_mark_associations": vector_mark_associations,
                    "native_lines": native_ordered_lines,
                    "ocr_lines": ocr_lines,
                    "spans": [span for _, _, _, _, spans in native_ordered_lines for span in spans],
                    "span_lines": [{"bbox": list(bbox), "text": text, "spans": spans} for _, _, text, bbox, spans in native_ordered_lines],
                    "fonts": [list(font) for font in page.get_fonts(full=True)],
                    "columns": column_texts,
                    "column_bounds": column_bounds,
                    "words": [word for word in page.get_text("words")],
                    "fraction_rules": fraction_rules,
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

                digest = hashlib.sha256(data).hexdigest()
                if digest in media_hashes:
                    media_duplicates.append({"source_page": page_number, "bbox": list(rect), "duplicate_of": media_hashes[digest], "reason": "Identical embedded image bytes were repeated in the source PDF."})
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
                    media_hashes[digest] = asset["asset_id"]

            drawing_regions = _cluster_drawing_rectangles(drawings, page.rect)

            for index, rect in enumerate(
                drawing_regions,
                start=1,
            ):
                crop_margin = max(0.0, float(settings.media_crop_margin_pt))
                clip = (
                    rect + (-crop_margin, -crop_margin, crop_margin, crop_margin)
                ) & page.rect

                pixmap = page.get_pixmap(
                    matrix=fitz.Matrix(2, 2),
                    clip=clip,
                    alpha=False,
                )

                image_data = pixmap.tobytes("png")
                digest = hashlib.sha256(image_data).hexdigest()
                if digest in media_hashes:
                    media_duplicates.append({"source_page": page_number, "bbox": list(clip), "duplicate_of": media_hashes[digest], "reason": "Identical vector crop bytes were repeated in the source PDF."})
                    continue

                asset = save_asset(
                    image_data,
                    media_dir,
                    f"p{page_number}_diagram{index}",
                    "diagram",
                    page_number,
                    clip,
                )

                if asset:
                    media.append(asset)
                    media_hashes[digest] = asset["asset_id"]

        return {
            "pages": pages,
            "media": media,
            "media_duplicates": media_duplicates,
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

        pending_numerators = question.pop("_pending_fraction_numerators", {})
        for option_id, fragments in pending_numerators.items():
            target = next((item for item in question["options"] if item["id"] == option_id), None)
            if target is None:
                continue
            for fragment, bbox in fragments:
                target.setdefault("_fragments", []).append({"text": fragment, "bbox": list(bbox)})
            if fragments:
                reason = "A stacked mathematical fragment had no geometrically supported denominator."
                target["review_required"] = True
                target["review_reasons"] = list(dict.fromkeys(target.get("review_reasons", []) + [reason]))
                question["review_reasons"] = list(dict.fromkeys(question.get("review_reasons", []) + [f"Option {option_id}: {reason}"]))

        question["options"].sort(key=lambda option: (not str(option["id"]).isdigit(), int(option["id"]) if str(option["id"]).isdigit() else str(option["id"])))
        for option in question["options"]:
            fragments = option.pop("_fragments", [])
            if fragments:
                option["original_text"] = option.get("original_text", option.get("text", ""))
                reflowed = _spatial_reflow_fragments(fragments)
                if reflowed:
                    option["text"] = reflowed
            # A role may have been initialized while the option was empty and
            # filled later from a superscript/fraction fragment. Recompute that
            # state from the final text and actual reasons instead of retaining
            # a stale blank-option flag.
            if option.get("text", "").strip() and not option.get("review_reasons"):
                option["review_required"] = bool(option.get("media"))

        question["source"]["regions"] = question.pop("_regions", [])

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
        devanagari_count = len(re.findall(r"[\u0900-\u097f]", raw_text))
        question["_source_language"] = "hi" if devanagari_count >= 4 and question["question"].get("hi") else "en"

        question["marks"] = marks

        option_ids = {option["id"] for option in question["options"]}
        is_mcq = bool(question.get("_option_started") or question["options"])
        question["question_type"] = "mcq" if is_mcq else "subjective"
        reasons = list(question.get("review_reasons", []))
        if not raw_text:
            reasons.append("Question text could not be extracted.")
        option_labels = [str(option["id"]) for option in question["options"]]
        numeric_labels = sorted({int(label) for label in option_labels if label.isdigit()})
        alpha_labels = sorted({label.upper() for label in option_labels if len(label) == 1 and label.upper() in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"})
        if len(numeric_labels) == len(option_labels) and numeric_labels and numeric_labels != list(range(numeric_labels[0], numeric_labels[-1] + 1)):
            reasons.append("Option numbering has a gap or duplicate; inspect the source option region.")
        if len(alpha_labels) == len(option_labels) and alpha_labels and alpha_labels != list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"[ord(alpha_labels[0]) - ord("A"):ord(alpha_labels[-1]) - ord("A") + 1]):
            reasons.append("Option lettering has a gap or duplicate; inspect the source option region.")
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
        if "\ufffd" in raw_text or any("\ufffd" in option.get("text", "") for option in question["options"]):
            reasons.append("One or more PDF glyphs decoded as replacement characters; inspect the original source region.")
        if _has_encoding_artifacts(raw_text) or any(_has_encoding_artifacts(option.get("text", "")) for option in question["options"]):
            reasons.append("One or more text fragments contain likely font or character-encoding artifacts; original source evidence is retained for review.")
        if re.search(r"(?:^|\s)(?:\u2192|\u20d7)(?:\s|$)|(?<![\w\u20d7])\u2192(?![\w\u20d7])", raw_text) or any(re.search(r"(?:^|\s)(?:\u2192|\u20d7)(?:\s|$)|(?<![\w\u20d7])\u2192(?![\w\u20d7])", option.get("text", "")) for option in question["options"]):
            reasons.append("A vector arrow is detached from its symbol in the extracted text.")
        compact_math = re.search(r"(?:[∫√→←↔∇]|[=+*/^])\s*(?:[=+*/^]|$)", raw_text)
        if compact_math:
            reasons.append("Mathematical notation may be fragmented in the extracted text.")
        if any(re.search(r"\d\s+\d\s*/\s*\d|\d/\d\s+\d/\d|(?:^|\s)[=+*/]\s{2,}", option.get("text", "")) for option in question["options"]):
            reasons.append("One or more options contain a suspiciously merged or incomplete mathematical expression.")
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
        question["extraction_confidence"] = None
        question["confidence"] = {
            "text_recognition": None,
            "mathematical_reconstruction": None,
            "question_grouping": None,
            "option_grouping": None,
            "media_association": None,
            "answer_association": None,
        }
        for option in question["options"]:
            option_text = option.get("text", "")
            option_math_suspicious = bool(_has_suspicious_math_layout(option_text) or re.search(r"(?:\d\s+\d\s*/\s*\d|\d/\d\s+\d/\d|(?:^|\s)[=+*/]\s{2,}|[A-Za-z)]\d(?:/|\b)|[=+\-−]\s*$)", option_text))
            option["confidence"] = {
                "text_recognition": None,
                "mathematical_reconstruction": None,
                "option_grouping": None,
                "media_association": None,
            }
            if option_math_suspicious:
                option["review_required"] = True
                option["review_reasons"] = list(dict.fromkeys(option.get("review_reasons", []) + ["Option contains suspicious mathematical fragments; inspect the source region."]))
                question["review_required"] = True
                question["review_reasons"] = list(dict.fromkeys(question["review_reasons"] + [f"Option {option['id']} contains suspicious mathematical fragments; inspect its source region."]))
        number = int(question["question_number"])
        question.pop("_option_started", None)
        question.pop("_option_anchors", None)
        question.pop("_option_anchor_pages", None)
        question.pop("_page_needs_review", None)
        existing = questions_by_number.get(number)
        if existing is None:
            question["source"]["language"] = question.pop("_source_language", "unknown")
            questions_by_number[number] = question
            current_section["questions"].append(question)
        else:
            prior_language = existing.get("source", {}).get("language", "unknown")
            incoming_language = question.pop("_source_language", "unknown")
            if prior_language == "unknown" or incoming_language == "en":
                existing.setdefault("source", {})["language"] = incoming_language
            prior_regions = existing.setdefault("source", {}).setdefault("regions", [])
            for region in question.get("source", {}).get("regions", []):
                if region not in prior_regions:
                    prior_regions.append(region)
            prior_content = existing.setdefault("source", {}).setdefault("content_bboxes", [])
            for region in question.get("source", {}).get("content_bboxes", []):
                if region not in prior_content:
                    prior_content.append(region)
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
                    prior.setdefault("source", {}).setdefault("alternate_texts", []).append({
                        "text": option["text"],
                        "source": option.get("source", {}),
                        "language": incoming_language,
                    })
                    if prior_language == "hi" and incoming_language == "en" and option["text"].strip():
                        prior["text"] = option["text"]
                        prior["original_text"] = option.get("original_text", option["text"])
                        prior["source"] = option.get("source", prior.get("source", {}))
                        prior["_fragments"] = option.get("_fragments", [])
                    elif prior_language == incoming_language:
                        reason = f"Repeated option {option['id']} has conflicting text in the same source language; the alternative was retained as evidence."
                        prior["review_required"] = True
                        prior["review_reasons"] = list(dict.fromkeys(prior.get("review_reasons", []) + [reason]))
                        question["review_reasons"] = list(dict.fromkeys(question.get("review_reasons", []) + [reason]))
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
        page_number = page["page"]
        positioned_lines = page.get("lines", [])
        line_order_y = {id(item[3]): item[0] for item in positioned_lines}
        if positioned_lines:
            page_lines = [(item[2], item[3]) for item in positioned_lines]
        else:
            page_lines = [(line, None) for line in page["text"].splitlines()]
        positioned_anchors = []
        page_option_anchors = []
        for anchor_line, anchor_bbox in page_lines:
            anchor_match = QUESTION_RE.match(anchor_line.replace("\u00a0", " ").strip())
            if anchor_match and anchor_bbox is not None:
                positioned_anchors.append((int(anchor_match.group(1)), line_order_y.get(id(anchor_bbox), anchor_bbox.y0), (anchor_bbox.x0 + anchor_bbox.x1) / 2))
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
            source_line_y = line_order_y.get(id(line_bbox), line_bbox.y0 if line_bbox is not None else 0)

            if not text:
                continue

            if re.fullmatch(r"Hindi\s*\+\s*English", text, re.IGNORECASE):
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
                    expected_number < number
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
                        "regions": [],
                        "content_bboxes": [],
                    },
                    "_regions": ([{
                        "page": page_number,
                        "bbox": list(line_bbox),
                        "column": _layout_column(line_bbox, page.get("width", 0)) if page.get("width") else "full",
                    }] if line_bbox is not None else []),
                    "_source_bbox": list(line_bbox) if line_bbox is not None else None,
                    "_option_started": False,
                    "_option_anchors": {},
                    "_option_anchor_pages": {},
                    "media": [],
                    "review_required": bool(page.get("needs_review")),
                    "review_reasons": (["The source page has an extraction or OCR warning."] if page.get("needs_review") else []),
                    "_page_needs_review": bool(page.get("needs_review")),
                    "_lines": carried_lines + pre_anchor_lines.pop(number, []) + ([initial_text] if initial_text else []),
                }
                if line_bbox is not None:
                    question["source"]["content_bboxes"].append({"page": page_number, "bbox": list(line_bbox)})

                continue

            if question is None:
                continue

            # Some PDFs place the body line a few points above its printed number.
            # Hold it for the upcoming same-column anchor instead of leaking it into
            # the prior question's final option.
            if line_bbox is not None:
                nearby_question_gap = 36 if len(text.split()) >= 4 and not numbered_options(text) else 12
                math_fragment = bool(
                    len(text) <= 36
                    and (
                        re.search(r"(?:\u2192|\u20d7|\^|\u00e2\u2020\u2019|\u00e2\u0192\u2014|[\u03b1-\u03c9\u0391-\u03a9]\s*/\s*\d|[\u2211-\u22ff])", text)
                        or re.fullmatch(r"(?:d[xy]|d2[xy]|[xy]2|[xy]_[xy])", text, re.IGNORECASE)
                    )
                )
                if question.get("_option_started") and math_fragment:
                    nearby_question_gap = 38
                formula_fragment = math_fragment or bool(
                    re.fullmatch(r"\([^)]{1,30}\)", text)
                    and re.search(r"[\d=^+*/\u2212\u00d7\u221a]", text)
                ) or bool(
                    # Vector components can be emitted as one multi-group line
                    # just above their printed question number. Preserve that
                    # line for the upcoming question when the same-column
                    # anchor is within the established geometric gap.
                    len(text) <= 110
                    and text.startswith(("(", "["))
                    and re.search(r"[=+×·√∫∑∏^]", text)
                    and ")" in text
                )
                upcoming = [
                    (anchor_number, anchor_y, anchor_x)
                    for anchor_number, anchor_y, anchor_x in positioned_anchors
                    if (
                        (
                            anchor_y >= source_line_y
                            and anchor_y - source_line_y <= nearby_question_gap
                        )
                        # Some math fonts give a complete vector expression a
                        # tall glyph box that straddles its printed question
                        # number. Compare the actual box, not its derived
                        # baseline, so that the expression is owned by the
                        # overlapping next-question anchor rather than the
                        # preceding question's final option.
                        or (
                            formula_fragment
                            and line_bbox.y0 < anchor_y < line_bbox.y1
                            and anchor_y - line_bbox.y0 <= nearby_question_gap
                        )
                    )
                    and anchor_number > int(question["question_number"])
                    and question.get("_source_bbox")
                    and (anchor_x >= page.get("width", 0) / 2) == ((line_bbox.x0 + line_bbox.x1) / 2 >= page.get("width", 0) / 2)
                ]
                overlaps_next_question_anchor = bool(
                    formula_fragment
                    and any(line_bbox.y0 < anchor_y < line_bbox.y1 for _, anchor_y, _ in upcoming)
                )
                owned_by_current_option = bool(
                    question.get("_option_started")
                    and any(
                        question.get("_option_anchor_pages", {}).get(option_id) == page_number
                        and source_line_y >= anchor_y
                        and source_line_y - anchor_y <= 22
                        and (anchor_x >= page.get("width", 0) / 2)
                        == ((line_bbox.x0 + line_bbox.x1) / 2 >= page.get("width", 0) / 2)
                        for option_id, (anchor_x, anchor_y) in question.get("_option_anchors", {}).items()
                    )
                )
                option_grid_continuation = bool(
                    question.get("_option_started")
                    and formula_fragment
                    and any(
                        option_id not in {str(item["id"]) for item in question.get("options", [])}
                        and 18 <= option_y - line_bbox.y0 <= 58
                        and abs(option_x - line_bbox.x0) <= max(72, line_bbox.height * 5)
                        and (option_x < page.get("width", 0) / 2)
                        == ((line_bbox.x0 + line_bbox.x1) / 2 < page.get("width", 0) / 2)
                        for option_id, option_x, option_y in page_option_anchors
                    )
                )
                if upcoming and (overlaps_next_question_anchor or not owned_by_current_option) and not option_grid_continuation and (not text.startswith(("(", "[")) or formula_fragment):
                    target_number = min(upcoming, key=lambda item: item[1])[0]
                    pre_anchor_lines.setdefault(target_number, []).append(text)
                    continue

            if line_bbox is not None and question.get("_source_bbox"):
                question_side = (question["_source_bbox"][0] + question["_source_bbox"][2]) / 2 >= page.get("width", 0) / 2
                line_side = (line_bbox.x0 + line_bbox.x1) / 2 >= page.get("width", 0) / 2
                if question_side != line_side:
                    # In bilingual two-column PDFs, a stem line can sit a few
                    # points above the same-number anchor in its own column.
                    # The opposite-column anchor may already have started this
                    # question, so preserve the line for the parallel anchor.
                    known_parallel_numbers = {
                        number for number, existing in questions_by_number.items()
                        if existing.get("source", {}).get("page") == page_number
                    }
                    parallel_anchors = [
                        (anchor_number, anchor_y)
                        for anchor_number, anchor_y, anchor_x in positioned_anchors
                        if anchor_number >= int(question["question_number"]) or anchor_number in known_parallel_numbers
                        and anchor_y >= source_line_y
                        and anchor_y - source_line_y <= 14
                        and (anchor_x >= page.get("width", 0) / 2) == line_side
                    ]
                    if parallel_anchors:
                        target_number = min(parallel_anchors, key=lambda item: item[1])[0]
                        pre_anchor_lines.setdefault(target_number, []).append(text)
                    continue

            # A raised numerator or the upper part of an option formula can
            # appear just before the option label in PDF reading order. Give
            # it to that next label only when its geometry is closer to a new
            # option anchor than to any option already opened for this question.
            if not numbered_options(text) and line_bbox is not None and question.get("_option_started"):
                present_ids = {str(item["id"]) for item in question["options"]}
                option_line_y = line_bbox.y0
                near_future = [
                    (option_id, x, y)
                    for option_id, x, y in page_option_anchors
                    if option_id not in present_ids
                    and option_line_y <= y <= option_line_y + 20
                    and abs(x - line_bbox.x0) <= max(80, line_bbox.height * 4)
                    and (x < page.get("width", 0) / 2)
                    == ((question["_source_bbox"][0] + question["_source_bbox"][2]) / 2 < page.get("width", 0) / 2)
                ]
                if near_future:
                    next_id, _, _ = min(near_future, key=lambda item: item[2] - option_line_y)
                    if re.search(r"[0-9=+\-−/√∫∑∏]|[A-Za-zα-ωΑ-Ω]", text):
                        pending_option_prefix.setdefault(next_id, []).append((text, line_bbox))
                        continue

            # Some physics papers print the formula first and its numbered
            # option marker below it. Associate such a formula with the label
            # in the same column using the repeated vertical layout, before it
            # can be absorbed into the question stem or a prior option.
            if not numbered_options(text) and line_bbox is not None and question.get("_source_bbox") and len(text) <= 80:
                option_line_y = line_bbox.y0
                math_content = bool(re.search(r"[=+×·√∫∑∏]|(?:\d\s*/\s*\d)", text))
                prose_words = re.findall(r"[A-Za-z]{3,}", text)
                nearby_prose = any(
                    other_bbox is not None
                    and other_text != text
                    and not QUESTION_RE.match(other_text.strip())
                    and not numbered_options(other_text.strip())
                    and len(re.findall(r"[A-Za-z]{2,}|[\u0900-\u097f]{2,}", other_text)) >= 3
                    and ((other_bbox.x0 + other_bbox.x1) / 2 >= page.get("width", 0) / 2)
                    == ((line_bbox.x0 + line_bbox.x1) / 2 >= page.get("width", 0) / 2)
                    and max(0, max(other_bbox.x0 - line_bbox.x1, line_bbox.x0 - other_bbox.x1)) <= 14
                    and max(0, max(other_bbox.y0 - line_bbox.y1, line_bbox.y0 - other_bbox.y1)) <= 8
                    for other_text, other_bbox in page_lines
                )
                if math_content and len(prose_words) <= 2 and not nearby_prose:
                    same_column = (line_bbox.x0 < page.get("width", 0) / 2) == (
                        (question["_source_bbox"][0] + question["_source_bbox"][2]) / 2 < page.get("width", 0) / 2
                    )
                    next_question_y = min(
                        (anchor_y for anchor_number, anchor_y, anchor_x in positioned_anchors
                         if anchor_number > int(question["question_number"])
                         and anchor_y >= option_line_y
                    and abs(anchor_x - (question["_source_bbox"][0] + question["_source_bbox"][2]) / 2) < page.get("width", 100000) * 0.25),
                        default=float("inf"),
                    )
                    future_option_labels = [
                        (option_id, x, y)
                        for option_id, x, y in page_option_anchors
                        if 18 <= y - option_line_y <= 58
                        and abs(x - line_bbox.x0) <= max(72, line_bbox.height * 5)
                        and same_column
                        and y < next_question_y
                    ]
                    if future_option_labels:
                        option_id, _, _ = min(
                            future_option_labels,
                            key=lambda item: (abs((item[2] - option_line_y) - 32), abs(item[1] - line_bbox.x0)),
                        )
                        pending_option_prefix.setdefault(option_id, []).append((text, line_bbox))
                        continue

            option_lines = numbered_options(text)

            isolated_numeric = bool(re.fullmatch(r"\d{1,3}", text))
            option_formula_prefix = bool(
                len(text) <= 24
                and re.search(r"[\d/=+^\u2212\u00b1\u00d7\u00f7\u221a\u222b\u2192\u2190]", text)
                and not re.search(r"[\u0900-\u097f]{2,}|\b(?:the|and|which|what|find|then)\b", text, re.IGNORECASE)
            )
            if option_formula_prefix and not option_lines and line_bbox is not None and not question.get("_option_started"):
                option_line_y = line_bbox.y0
                future_question_y = min(
                    (anchor_y for anchor_number, anchor_y, anchor_x in positioned_anchors
                     if anchor_number > int(question["question_number"])
                     and anchor_y > option_line_y
                     and abs(anchor_x - question["_source_bbox"][0]) < page.get("width", 100000) * 0.18),
                    default=float("inf"),
                )
                candidate_anchors = {
                    option_id: (x, y)
                    for option_id, x, y in page_option_anchors
                    if option_line_y <= y <= option_line_y + 18 and y < future_question_y
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
                option_line_y = line_bbox.y0
                future_question_y = min(
                    (anchor_y for anchor_number, anchor_y, anchor_x in positioned_anchors
                     if anchor_number > int(question["question_number"])
                     and anchor_y > option_line_y
                     and abs(anchor_x - question["_source_bbox"][0]) < page.get("width", 100000) * 0.18),
                    default=float("inf"),
                )
                candidate_anchors = {
                    option_id: (x, y)
                    for option_id, x, y in page_option_anchors
                    if option_line_y <= y <= option_line_y + 18 and y < future_question_y
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
                    fragment_bbox = None
                    if line_bbox is not None and marker_x is not None:
                        marker_width = max(7, min(18, line_bbox.height * 0.8))
                        marker_bbox = fitz.Rect(marker_x, line_bbox.y0, min(line_bbox.x1, marker_x + marker_width), line_bbox.y1)
                        later_offsets = [item["offset"] for item in option_lines if item["offset"] > option["offset"]]
                        content_x1 = line_bbox.x0 + (min(later_offsets) / max(1, len(text))) * line_bbox.width if later_offsets else line_bbox.x1
                        content_x0 = min(line_bbox.x1, marker_x + marker_width)
                        fragment_bbox = fitz.Rect(content_x0, line_bbox.y0, max(content_x0, content_x1), line_bbox.y1)
                    existing_option = next((item for item in question["options"] if item["id"] == option["id"]), None)
                    if existing_option is None:
                        new_option = {
                            "id": option_id,
                            "text": option_text,
                            "original_text": option_text,
                            "media": [],
                            "source": {"page": page_number, "bbox": list(marker_bbox) if marker_bbox is not None else None, "content_bboxes": [list(line_bbox)] if line_bbox is not None else []},
                            "review_required": not bool(option_text),
                        }
                        if option_text and fragment_bbox is not None:
                            new_option["_fragments"] = [{"text": option_text, "bbox": list(fragment_bbox)}]
                        question["options"].append(new_option)
                        if marker_x is not None:
                            question["_option_anchors"][option_id] = (marker_x, line_bbox.y0)
                            question["_option_anchor_pages"][option_id] = page_number
                    elif option_text and existing_option["text"] != option_text:
                        old_has_latin = bool(re.search(r"[A-Za-z]", existing_option["text"]))
                        new_has_latin = bool(re.search(r"[A-Za-z]", option_text))
                        if new_has_latin and not old_has_latin:
                            existing_option["text"] = option_text
                            existing_option["_fragments"] = ([{"text": option_text, "bbox": list(fragment_bbox)}] if option_text and fragment_bbox is not None else [])
                        elif old_has_latin == new_has_latin:
                            question["review_required"] = True
                    question["_option_started"] = True
                    if line_bbox is not None:
                        question["source"].setdefault("content_bboxes", []).append({"page": page_number, "bbox": list(line_bbox)})
                    pending_fragments = sorted(pending_option_prefix.pop(option_id, []), key=lambda item: (item[1].y0, item[1].x0))
                    if pending_fragments:
                        option_record = next((item for item in question["options"] if item["id"] == option_id), None)
                        if option_record is not None:
                            marker_x = fitz.Rect(option_record["source"]["bbox"]).x0 if option_record["source"].get("bbox") else 0
                            left_fragments = [fragment for fragment, fragment_bbox in pending_fragments if fragment_bbox.x0 <= marker_x + 36]
                            right_fragments = [fragment for fragment, fragment_bbox in pending_fragments if fragment_bbox.x0 > marker_x + 36]
                            option_record["text"] = " ".join(part for part in (" ".join(left_fragments), option_record["text"], " ".join(right_fragments)) if part)
                            option_record["original_text"] = option_record["text"]
                            option_record.setdefault("_fragments", []).extend(
                                {"text": fragment, "bbox": list(fragment_bbox)}
                                for fragment, fragment_bbox in pending_fragments
                            )
                            option_record.setdefault("source", {}).setdefault("content_bboxes", []).extend(list(fragment_bbox) for _, fragment_bbox in pending_fragments)
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
                        fraction_bbox = None
                        if text.strip().isdigit() and line_bbox is not None:
                            for numerator, numerator_bbox in numerators:
                                numerator_rect = fitz.Rect(numerator_bbox)
                                for rule_values in page.get("fraction_rules", []):
                                    rule = fitz.Rect(rule_values)
                                    if numerator_rect.y1 <= rule.y0 <= line_bbox.y1 and rule.x1 >= numerator_rect.x0 and rule.x0 <= line_bbox.x1:
                                        fraction = f"{numerator}/{text.strip()}"
                                        fraction_bbox = numerator_rect | line_bbox
                                        break
                                denominator_center = (line_bbox.x0 + line_bbox.x1) / 2
                                numerator_center = (numerator_rect.x0 + numerator_rect.x1) / 2
                                vertical_gap = line_bbox.y0 - numerator_rect.y1
                                aligned_stack = abs(denominator_center - numerator_center) <= 8 and 0 <= vertical_gap <= 20
                                if aligned_stack:
                                    fraction = f"{numerator}/{text.strip()}"
                                    fraction_bbox = numerator_rect | line_bbox
                                if fraction:
                                    break
                        addition = fraction or text
                        option["text"] = " ".join(part for part in (option["text"], addition) if part)
                        if addition and (line_bbox is not None or fraction_bbox is not None):
                            fragment_bbox = fraction_bbox or line_bbox
                            option.setdefault("_fragments", []).append({"text": addition, "bbox": list(fragment_bbox)})
                        if fraction:
                            question["_pending_fraction_numerators"][option_id].remove(next(item for item in numerators if item[0] == fraction.split("/", 1)[0]))
                        if line_bbox is not None:
                            option.setdefault("source", {}).setdefault("content_bboxes", []).append(list(line_bbox))
                            question["source"].setdefault("content_bboxes", []).append({"page": page_number, "bbox": list(line_bbox)})
                        option["original_text"] = option["text"]
                        option["review_required"] = not bool(option["text"].strip())
                    continue
            question["_lines"].append(text)
            if line_bbox is not None:
                question["source"].setdefault("content_bboxes", []).append({"page": page_number, "bbox": list(line_bbox)})

    flush_question()

    if current_section["questions"]:
        sections.append(current_section)

    # Use a section's repeated label pattern as evidence of missing options.
    # A lone three-choice question remains valid; a deviation is only flagged
    # when another question establishes a longer option-label pattern.
    for section in sections:
        patterns = [
            tuple(str(option["id"]) for option in question.get("options", []))
            for question in section["questions"]
            if question.get("question_type") == "mcq"
        ]
        repeated = Counter(pattern for pattern in patterns if len(pattern) >= 3)
        if not repeated:
            continue
        expected_pattern, occurrences = repeated.most_common(1)[0]
        if occurrences < 1:
            continue
        for question in section["questions"]:
            if question.get("question_type") != "mcq":
                continue
            actual = tuple(str(option["id"]) for option in question.get("options", []))
            if actual and set(actual) < set(expected_pattern):
                reason = f"This question has fewer option labels than the section's recurring pattern ({', '.join(expected_pattern)}); verify whether the source has omitted choices."
                question["review_reasons"] = list(dict.fromkeys(question.get("review_reasons", []) + [reason]))
                question["review_required"] = True

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
    padding = max(0.0, float(settings.media_crop_margin_pt))
    content_rectangles = [fitz.Rect(values) for values in option.get("source", {}).get("content_bboxes", []) if len(values) == 4]
    # When legacy-font/vector formula content is undecoded, the option marker
    # can be the only native-text bbox. Treat it as no recovered body so the
    # source crop spans this option cell instead of capturing only “(3)”.
    content_rectangles = [
        rect for rect in content_rectangles
        if not (rect.x0 >= marker.x0 - 2 and rect.x1 <= marker.x1 + 2 and abs(rect.y0 - marker.y0) <= 3)
    ]
    content_region = fitz.Rect(content_rectangles[0]) if content_rectangles else None
    for component in content_rectangles[1:]:
        content_region |= component
    same_row = [
        fitz.Rect(other["source"]["bbox"])
        for other in question["options"]
        if other is not option and other.get("source", {}).get("bbox")
        and abs(fitz.Rect(other["source"]["bbox"]).y0 - marker.y0) <= 10
    ]
    right_candidates = [rect.x0 for rect in same_row if rect.x0 > marker.x0]
    column_right = page_width / 2 if marker.x0 < page_width / 2 else page_width - 24
    if content_region is not None:
        x0 = max(0, min(marker.x0, content_region.x0) - padding)
        x1 = min(max(marker.x1, content_region.x1) + padding, min(right_candidates, default=column_right) - 2)
    else:
        x0 = max(0, marker.x0 - padding)
        x1 = min(right_candidates, default=column_right) - 2
    later_rows = [
        fitz.Rect(other["source"]["bbox"]).y0
        for other in question["options"]
        if other is not option and other.get("source", {}).get("bbox")
        and fitz.Rect(other["source"]["bbox"]).y0 > marker.y0 + 10
        and _layout_column(fitz.Rect(other["source"]["bbox"]), page_width) == _layout_column(marker, page_width)
    ]
    marker_column = _layout_column(marker, page_width)
    next_questions = [
        float(line[0])
        for line in page_data.get("lines", [])
        if (match := QUESTION_RE.match(line[2].replace("\u00a0", " ").strip()))
        and int(match.group(1)) > int(question["question_number"])
        and line[0] > marker.y0
        and (marker_column == "full" or _layout_column(line[3], page_width) in (marker_column, "full"))
    ]
    content_y0 = min([marker.y0] + [rect.y0 for rect in content_rectangles])
    content_y1 = max([marker.y1] + [rect.y1 for rect in content_rectangles]) if content_rectangles else None
    cell_end = min([row for row in later_rows] + next_questions + [page_height - 12])
    y0 = max(0, content_y0 - padding)
    option_extent = content_y1 + padding if content_y1 is not None else marker.y0 + 42
    y1 = min(cell_end - padding, option_extent)
    clip = fitz.Rect(x0, y0, x1, y1)
    if clip.width < 18 or clip.height < 12:
        return None
    try:
        source_page = source_document[page_number - 1]
        clip &= source_page.rect
        crop_scale = max(2.0, min(6.0, float(settings.math_crop_dpi) / 72))
        pixmap = source_page.get_pixmap(matrix=fitz.Matrix(crop_scale, crop_scale), clip=clip, alpha=False)
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
            "pixel_width": pixmap.width,
            "pixel_height": pixmap.height,
            "extraction_method": "source-page region render",
            "confidence": None,
            "review_reasons": ["Source crop supplements text extraction and requires human visual review."],
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

    questions = [question for section in sections for question in section["questions"]]
    asset_candidates: dict[str, list[tuple[float, dict, dict]]] = {}
    for question in questions:
        number = int(question["question_number"])
        source_regions = question.get("source", {}).get("regions", [])
        if not source_regions:
            source_bbox = question.get("source", {}).get("bbox")
            if source_bbox:
                source_regions = [{
                    "page": question.get("source", {}).get("page"),
                    "bbox": source_bbox,
                    "column": "full",
                }]

        for region in source_regions:
            page_number = region.get("page")
            page = page_map.get(page_number)
            if page is None or not region.get("bbox"):
                continue
            anchor = fitz.Rect(region["bbox"])
            page_width = float(page.get("width", 0) or 0)
            column = region.get("column") or _layout_column(anchor, page_width)
            next_positions = []
            for line in page.get("lines", []):
                match = QUESTION_RE.match(line[2].replace("\u00a0", " ").strip())
                if not match or int(match.group(1)) <= number or line[0] <= anchor.y0:
                    continue
                next_bbox = line[3]
                next_column = _layout_column(next_bbox, page_width) if page_width else "full"
                if column == "full" or next_column == column or next_column == "full":
                    next_positions.append(line[0])
            end_y = min(next_positions, default=float(page.get("height", anchor.y1 + 1)))

            for asset in media:
                if asset.get("source_page") != page_number or not asset.get("bbox"):
                    continue
                if asset.get("type") == "diagnostic_page":
                    continue
                asset_rect = fitz.Rect(asset["bbox"])
                asset_column = _layout_column(asset_rect, page_width) if page_width else "full"
                if column != "full" and asset_column not in (column, "full"):
                    continue
                if not (asset_rect.y0 >= anchor.y0 - 12 and asset_rect.y0 < end_y and asset_rect.y1 <= end_y + 12):
                    continue
                vertical_gap = max(anchor.y0 - asset_rect.y1, asset_rect.y0 - anchor.y1, 0)
                horizontal_gap = max(anchor.x0 - asset_rect.x1, asset_rect.x0 - anchor.x1, 0)
                score = vertical_gap + min(horizontal_gap, page_width if page_width else horizontal_gap)
                asset_candidates.setdefault(asset["asset_id"], []).append((score, question, {**asset, "source_page": page_number}))

    # A single source asset is assigned once. If geometry cannot distinguish
    # between nearby questions, retain it in the manifest as unassociated.
    for asset_id, candidates in asset_candidates.items():
        unique_candidates = {}
        for score, question, asset in candidates:
            unique_candidates[question["question_id"]] = min(
                unique_candidates.get(question["question_id"], (float("inf"), question, asset)),
                (score, question, asset),
                key=lambda item: item[0],
            )
        ranked = sorted(unique_candidates.values(), key=lambda item: item[0])
        if len(ranked) > 1 and ranked[1][0] - ranked[0][0] <= 8:
            reason = f"Media asset {asset_id} falls in overlapping question regions; association was left unresolved."
            for _, question, _ in ranked[:2]:
                question["review_reasons"] = list(dict.fromkeys(question.get("review_reasons", []) + [reason]))
                question["review_required"] = True
            continue
        _, question, asset = ranked[0]
        if not any(item.get("asset_id") == asset_id for item in question["media"]):
            question["media"].append(asset)

    for question in questions:
        page_number = question.get("source", {}).get("page")
        page = page_map.get(page_number)
        if not page:
            continue

        if page is None:
            continue
        english_stem = question.get("question", {}).get("en") or ""
        if question["media"] and (len(english_stem.strip()) < 28 or re.fullmatch(r"(?:shown in the figure|as shown in figure|shown in figure)\s*[:-]?", english_stem.strip(), re.IGNORECASE)):
            reason = "Question text is unusually short for a figure-based question; verify that the complete stem is present."
            question["review_reasons"] = list(dict.fromkeys(question.get("review_reasons", []) + [reason]))
            question["review_required"] = True

        # Associate a diagram with the nearest option only when the geometry is
        # sufficiently clear. Do not let the first option in list order win.
        assigned_assets = set()
        boxed_options = [
            (option, fitz.Rect(option["source"]["bbox"]))
            for option in question["options"]
            if option.get("source", {}).get("bbox")
        ]
        for asset in question["media"]:
            if asset.get("type") != "diagram" or not asset.get("bbox"):
                continue
            asset_rect = fitz.Rect(asset["bbox"])
            candidates = []
            for option, option_rect in boxed_options:
                horizontal_gap = max(option_rect.x0 - asset_rect.x1, asset_rect.x0 - option_rect.x1, 0)
                vertical_gap = max(option_rect.y0 - asset_rect.y1, asset_rect.y0 - option_rect.y1, 0)
                overlaps_inline = option_rect.y0 <= asset_rect.y1 and asset_rect.y0 <= option_rect.y1
                if horizontal_gap <= 48 and vertical_gap <= 52 and (overlaps_inline or asset_rect.y0 >= option_rect.y1):
                    candidates.append((horizontal_gap + vertical_gap, option))
            candidates.sort(key=lambda item: item[0])
            if not candidates:
                continue
            if len(candidates) > 1 and candidates[1][0] - candidates[0][0] <= 8:
                reason = f"Diagram {asset.get('asset_id')} is close to multiple options; option association was left unresolved."
                question["review_reasons"] = list(dict.fromkeys(question.get("review_reasons", []) + [reason]))
                question["review_required"] = True
                continue
            _, option = candidates[0]
            option["media"].append(dict(asset))
            option["review_required"] = True
            option.setdefault("review_reasons", []).append("Nearby vector diagram association is geometry-based and requires visual review.")
            assigned_assets.add(asset.get("asset_id"))
        if assigned_assets:
            question["media"] = [asset for asset in question["media"] if asset.get("asset_id") not in assigned_assets]
            if all(option["text"].strip() or option["media"] for option in question["options"]):
                question["review_reasons"] = [
                    reason for reason in question.get("review_reasons", [])
                    if reason != "One or more options have neither readable text nor associated media."
                ]
                question["review_required"] = bool(question["review_reasons"])

        for option in question["options"]:
            option_text = option.get("text", "")
            suspicious_math = bool(_has_encoding_artifacts(option_text) or _has_displaced_short_option_content(option) or _has_suspicious_math_layout(option_text) or re.search(r"(?:\d\s+\d\s*/\s*\d|\d/\d\s+\d/\d|(?:^|\s)[=+*/]\s{2,}|[A-Za-z)]\d(?:/|\b)|[=+\-−]\s*$)", option_text))
            if option.get("media") or (option_text.strip() and not suspicious_math):
                continue
            crop = _crop_option_source(option, question, page, source_document, media_dir)
            if crop:
                option["media"].append(crop)
                option["review_required"] = True
                reason = f"Option {option['id']} has a source crop for verification because its mathematical text may be incomplete."
                option["review_reasons"] = list(dict.fromkeys(option.get("review_reasons", []) + [reason]))
                option.setdefault("math_evidence", []).append({
                    "original_text": option.get("original_text") or option_text,
                    "reconstructed_text": None,
                    "normalized_text": None,
                    "latex": None,
                    "mathml": None,
                    "source_page": crop.get("source_page"),
                    "source_bbox": crop.get("bbox"),
                    "component_bboxes": option.get("source", {}).get("content_bboxes", []),
                    "extraction_method": "high_resolution_source_region_render",
                    "confidence": None,
                    "review_required": True,
                    "review_reasons": [reason],
                })
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


def verify_suspicious_option_crops(sections, media_dir: Path) -> dict:
    """Attach untrusted Ollama transcripts as review evidence; never replace source text."""
    summary = {
        "enabled": bool(settings.ollama_enabled),
        "available": False,
        "model": settings.ollama_model if settings.ollama_enabled else None,
        "used": False,
        "regions_attempted": 0,
        "regions_completed": 0,
        "warnings": [],
    }
    if not settings.ollama_enabled:
        return summary

    import httpx

    try:
        response = httpx.get(
            f"{settings.ollama_base_url.rstrip('/')}/api/tags",
            timeout=min(8.0, settings.ollama_timeout_seconds),
        )
        response.raise_for_status()
        model_names = {item.get("name") for item in response.json().get("models", [])}
        summary["available"] = settings.ollama_model in model_names
        if not summary["available"]:
            summary["warnings"].append(f"Configured Ollama model {settings.ollama_model!r} is unavailable; visual verification was skipped.")
            return summary
    except Exception as error:
        summary["warnings"].append(f"Ollama is enabled but unavailable: {type(error).__name__}: {error}")
        return summary

    for section in sections:
        for question in section["questions"]:
            for option in question.get("options", []):
                crops = [asset for asset in option.get("media", []) if asset.get("type") == "option_crop"]
                if not crops:
                    continue
                crop = crops[0]
                image_path = media_dir / crop["filename"]
                if not image_path.is_file():
                    summary["warnings"].append(f"Source crop for Q{question['question_number']} option {option['id']} is missing; visual verification skipped.")
                    continue
                summary["regions_attempted"] += 1
                try:
                    candidate = verify_math_image(
                        image_path,
                        base_url=settings.ollama_base_url,
                        model=settings.ollama_model,
                        timeout_seconds=settings.ollama_timeout_seconds,
                    )
                    summary["used"] = True
                    summary["regions_completed"] += 1
                    native = re.sub(r"\s+", "", option.get("text", "")).casefold()
                    visual = re.sub(r"\s+", "", candidate["candidate_transcription"]).casefold()
                    matches = bool(native) and native in visual or bool(visual) and visual in native
                    option["vision_verification"] = {
                        **candidate,
                        "candidate_matches_extracted_text": matches,
                        "accepted_as_reconstruction": False,
                    }
                    option.setdefault("math_evidence", []).append({
                        "original_text": option.get("original_text") or option.get("text", ""),
                        "reconstructed_text": None,
                        "normalized_text": None,
                        "latex": None,
                        "mathml": None,
                        "source_page": crop.get("source_page"),
                        "source_bbox": crop.get("bbox"),
                        "component_bboxes": [crop.get("bbox")] if crop.get("bbox") else [],
                        "extraction_method": "ollama_qwen_visual_candidate",
                        "confidence": None,
                        "review_required": True,
                        "review_reasons": ["Vision transcription is an unaccepted candidate; compare it with the original PDF crop."],
                        "vision_candidate": candidate["candidate_transcription"],
                    })
                    if not matches:
                        reason = "Local vision transcription differs from extracted option text; manual source review is required."
                        option["review_required"] = True
                        option["review_reasons"] = list(dict.fromkeys(option.get("review_reasons", []) + [reason]))
                        question["review_required"] = True
                        question["review_reasons"] = list(dict.fromkeys(question.get("review_reasons", []) + [f"Option {option['id']}: {reason}"]))
                except Exception as error:
                    summary["warnings"].append(f"Visual verification failed for Q{question['question_number']} option {option['id']}: {type(error).__name__}: {error}")
    if summary["regions_attempted"] > summary["regions_completed"]:
        summary["warnings"].append(f"Visual verification completed for {summary['regions_completed']} of {summary['regions_attempted']} suspicious option crops.")
    return summary


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
        vision_verification = verify_suspicious_option_crops(sections, root / "media")
        for section in sections:
            for parsed_question in section["questions"]:
                # Keep source coordinates in output for audit/debugging.
                parsed_question.pop("_option_started", None)
                parsed_question.pop("_option_anchors", None)
                parsed_question.pop("_option_anchor_pages", None)
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
                parsed_question.setdefault("confidence", {})["answer_association"] = 1.0
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
        extraction_warnings.extend(vision_verification["warnings"])
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
                "vision_verification": vision_verification,
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

        referenced_by_file = {}
        for section in result["sections"]:
            for parsed_question in section["questions"]:
                for scope, collection in (("question", parsed_question.get("media", [])), ("option", [asset for option in parsed_question.get("options", []) for asset in option.get("media", [])])):
                    for asset in collection:
                        row = referenced_by_file.setdefault(asset["filename"], {"question_id": parsed_question["question_id"], "question_number": parsed_question["question_number"], "option_id": None, "association_scope": scope})
                        if scope == "option":
                            for option in parsed_question.get("options", []):
                                if any(item["filename"] == asset["filename"] for item in option.get("media", [])):
                                    row["option_id"] = option["id"]
                                    break
        asset_by_filename = {asset["filename"]: asset for asset in document_data.get("media", [])}
        manifest_assets = []
        media_dir = root / "media"
        for media_file in sorted(media_dir.iterdir() if media_dir.exists() else []):
            if not media_file.is_file():
                continue
            metadata = asset_by_filename.get(media_file.name, {})
            association = referenced_by_file.get(media_file.name)
            try:
                with Image.open(media_file) as image:
                    pixel_width, pixel_height = image.size
                    media_type = image.format.lower()
            except Exception:
                pixel_width = pixel_height = None
                media_type = "unknown"
            manifest_assets.append({
                "asset_id": metadata.get("asset_id", media_file.stem),
                "filename": media_file.name,
                "source_page": metadata.get("source_page"),
                "source_bbox": metadata.get("bbox"),
                "pixel_dimensions": {"width": pixel_width, "height": pixel_height},
                "media_type": media_type,
                "purpose": metadata.get("type", "option_crop" if "_option_" in media_file.name else "diagnostic_evidence"),
                "associated_question_id": association.get("question_id") if association else None,
                "associated_question_number": association.get("question_number") if association else None,
                "associated_option_id": association.get("option_id") if association else None,
                "association_scope": association.get("association_scope") if association else None,
                "extraction_method": metadata.get("extraction_method", "high-resolution PDF region rendering"),
                "confidence": metadata.get("confidence"),
                "review_reasons": metadata.get("review_reasons", []) if association else ["Asset is retained as evidence but is not associated with a question or option."],
            })
        media_manifest = {
            "assets": manifest_assets,
            "duplicate_occurrences": document_data.get("media_duplicates", []),
            "unassociated_assets": [asset["filename"] for asset in manifest_assets if not asset["associated_question_id"]],
        }
        (root / "media_manifest.json").write_text(json.dumps(media_manifest, ensure_ascii=False, indent=2), encoding="utf-8")

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
