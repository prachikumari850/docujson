"""Source-backed SVG generation and honest raster wrappers.

PDF vector SVGs in this module are generated only from PyMuPDF drawing
primitives. Raster wrappers are explicitly identified and never reported as
vector reconstruction. The original raster crop remains alongside either
representation as a visual fallback.
"""
from __future__ import annotations

import html
import logging
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import fitz
from PIL import Image

logger = logging.getLogger("docujson.svg")
SVG_NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG_NS)
SUPPORTED_RASTER_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg"}


def _n(value: float) -> str:
    if not math.isfinite(float(value)):
        raise ValueError("Non-finite SVG coordinate")
    return f"{float(value):.3f}".rstrip("0").rstrip(".") or "0"


def _color(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, (tuple, list)) or len(value) < 3:
        return None
    channels = [max(0, min(255, round(float(part) * 255))) for part in value[:3]]
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def _xy(point: Any, clip: fitz.Rect) -> tuple[float, float]:
    return float(point.x - clip.x0), float(point.y - clip.y0)


def _path_for_drawing(drawing: dict[str, Any], clip: fitz.Rect) -> str | None:
    commands: list[str] = []
    for item in drawing.get("items", []):
        if not item:
            continue
        kind = item[0]
        if kind == "l":
            x1, y1 = _xy(item[1], clip)
            x2, y2 = _xy(item[2], clip)
            commands.append(f"M {_n(x1)} {_n(y1)} L {_n(x2)} {_n(y2)}")
        elif kind == "c":
            points = [_xy(point, clip) for point in item[1:5]]
            commands.append(
                f"M {_n(points[0][0])} {_n(points[0][1])} "
                f"C {_n(points[1][0])} {_n(points[1][1])} "
                f"{_n(points[2][0])} {_n(points[2][1])} "
                f"{_n(points[3][0])} {_n(points[3][1])}"
            )
        elif kind == "re":
            rect = fitz.Rect(item[1])
            x, y = rect.x0 - clip.x0, rect.y0 - clip.y0
            w, h = rect.width, rect.height
            if w < 0 or h < 0:
                return None
            commands.append(
                f"M {_n(x)} {_n(y)} h {_n(w)} v {_n(h)} "
                f"h {_n(-w)} Z"
            )
        elif kind == "qu":
            quad = item[1]
            points = [quad.ul, quad.ur, quad.lr, quad.ll]
            mapped = [_xy(point, clip) for point in points]
            commands.append(
                f"M {_n(mapped[0][0])} {_n(mapped[0][1])} "
                + " ".join(f"L {_n(x)} {_n(y)}" for x, y in mapped[1:])
                + " Z"
            )
        else:
            # Do not silently approximate an unsupported primitive.
            return None
    if drawing.get("closePath") and commands:
        commands[-1] += " Z"
    return " ".join(commands) or None


def reconstruct_pdf_vector_svg(
    page: fitz.Page,
    drawings: list[dict[str, Any]],
    clip: fitz.Rect,
    svg_path: Path,
) -> dict[str, Any] | None:
    """Write genuine path-based SVG for the PDF paths intersecting ``clip``.

    Unsupported drawing commands, empty geometry, or paths representing a
    page-sized background cause a raster fallback. Text labels are copied as
    text elements from native PDF text spans; OCR is deliberately not used.
    """
    clip = fitz.Rect(clip) & page.rect
    if clip.is_empty or clip.width <= 0 or clip.height <= 0 or page.rotation != 0:
        return None

    selected: list[dict[str, Any]] = []
    for drawing in drawings:
        rect = fitz.Rect(drawing.get("rect", (0, 0, 0, 0)))
        if rect.is_empty or not rect.intersects(clip):
            continue
        # Page-wide separators and borders can cross a small option crop at
        # its edge. Treating that sliver as local vector content produced a
        # misleading one-line SVG for image-backed arrow options. A drawing
        # primitive must have a spatial extent local to the crop to qualify.
        if rect.width > max(clip.width * 4, clip.width + 80) or rect.height > max(clip.height * 4, clip.height + 80):
            continue
        # Exclude background/page-wide drawing objects that merely cross a
        # candidate crop. They are not evidence of local diagram geometry.
        if rect.width * rect.height > max(clip.width * clip.height * 6, page.rect.width * page.rect.height * 0.20):
            continue
        selected.append(drawing)

    paths: list[str] = []
    for drawing in selected:
        path = _path_for_drawing(drawing, clip)
        if path is None:
            # If an unsupported primitive is part of this candidate, retain
            # the original raster rather than emit a partial/misleading SVG.
            return None
        if not path:
            continue
        color = _color(drawing.get("color"))
        fill = _color(drawing.get("fill"))
        if color is None and fill is None:
            continue
        attrs = [f'd="{html.escape(path, quote=True)}"']
        attrs.append(f'fill="{fill or "none"}"')
        attrs.append(f'stroke="{color or "none"}"')
        width = drawing.get("width")
        if color is not None and width is not None:
            attrs.append(f'stroke-width="{_n(max(0.05, float(width)))}"')
        cap_map = {0: "butt", 1: "round", 2: "square"}
        join_map = {0: "miter", 1: "round", 2: "bevel"}
        line_cap = drawing.get("lineCap")
        if isinstance(line_cap, (tuple, list)):
            line_cap = line_cap[-1] if line_cap else None
        if line_cap is not None and int(line_cap) in cap_map:
            attrs.append(f'stroke-linecap="{cap_map[int(line_cap)]}"')
        line_join = drawing.get("lineJoin")
        if line_join is not None and int(line_join) in join_map:
            attrs.append(f'stroke-linejoin="{join_map[int(line_join)]}"')
        dash = drawing.get("dashes")
        if isinstance(dash, str):
            match = re.search(r"\[([^]]*)\]\s*([-+\d.]+)?", dash)
            if match:
                dash_values = re.findall(r"[-+]?\d*\.?\d+", match.group(1))
                if dash_values:
                    attrs.append(f'stroke-dasharray="{html.escape(" ".join(dash_values), quote=True)}"')
                if match.group(2):
                    attrs.append(f'stroke-dashoffset="{html.escape(match.group(2), quote=True)}"')
        for key, attr in (("stroke_opacity", "stroke-opacity"), ("fill_opacity", "fill-opacity")):
            opacity = drawing.get(key)
            if opacity is not None:
                attrs.append(f'{attr}="{_n(max(0, min(1, float(opacity))))}"')
        if drawing.get("even_odd"):
            attrs.append('fill-rule="evenodd"')
        paths.append("<path " + " ".join(attrs) + "/>")

    if not paths:
        return None

    text_elements: list[str] = []
    text_dict = page.get_text("dict", clip=clip, sort=False)
    drawing_boxes = [fitz.Rect(item.get("rect", (0, 0, 0, 0))) for item in selected]
    for block in text_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "")
                origin = span.get("origin")
                if not text or not origin:
                    continue
                span_box = fitz.Rect(span.get("bbox", (0, 0, 0, 0)))
                covered = sum(
                    (span_box & path_box).get_area()
                    for path_box in drawing_boxes
                    if path_box.intersects(span_box)
                    and path_box.width <= span_box.width * 0.55
                    and path_box.height <= span_box.height * 1.4
                )
                # Some PDFs contain both native text and vector outlines for
                # the same glyphs. Keep the outlined source glyphs and avoid
                # painting a duplicate <text> layer over them.
                if span_box.get_area() and min(1.0, covered / span_box.get_area()) >= 0.35:
                    continue
                x, y = float(origin[0]) - clip.x0, float(origin[1]) - clip.y0
                size = max(1.0, float(span.get("size", 10)))
                color = _color(tuple(((span.get("color", 0) >> shift) & 255) / 255 for shift in (16, 8, 0)))
                escaped = html.escape(text, quote=False)
                font = html.escape(str(span.get("font", "sans-serif")).split(",", 1)[0], quote=True)
                flags = int(span.get("flags", 0) or 0)
                font_weight = "bold" if flags & 16 else "normal"
                font_style = "italic" if flags & 2 else "normal"
                text_elements.append(
                    f'<text x="{_n(x)}" y="{_n(y)}" font-size="{_n(size)}" font-family="{font}" '
                    f'font-weight="{font_weight}" font-style="{font_style}" '
                    f'fill="{color or "#000000"}">{escaped}</text>'
                )

    width, height = clip.width, clip.height
    body = "".join(paths) + "".join(text_elements)
    svg = (
        f'<svg xmlns="{SVG_NS}" width="{_n(width)}pt" height="{_n(height)}pt" '
        f'viewBox="0 0 {_n(width)} {_n(height)}" preserveAspectRatio="xMidYMid meet">'
        f'<title>PDF vector reconstruction, page {page.number + 1}</title>'
        f'<defs><clipPath id="source-region"><rect x="0" y="0" width="{_n(width)}" height="{_n(height)}"/></clipPath></defs>'
        f'<g clip-path="url(#source-region)">{body}</g></svg>'
    )
    svg_path = Path(svg_path)
    svg_path.write_text(svg, encoding="utf-8", newline="\n")
    try:
        root = ET.parse(svg_path).getroot()
    except ET.ParseError:
        svg_path.unlink(missing_ok=True)
        return None
    if root.tag != f"{{{SVG_NS}}}svg" or root.find(f".//{{{SVG_NS}}}image") is not None:
        svg_path.unlink(missing_ok=True)
        return None
    vector_count = sum(root.find(f".//{{{SVG_NS}}}{tag}") is not None for tag in ("path", "line", "polyline", "polygon", "circle", "ellipse"))
    if not vector_count:
        svg_path.unlink(missing_ok=True)
        return None
    return {
        "filename": svg_path.name,
        "media_type": "image/svg+xml",
        "representation": "svg_vector",
        "svg_generation_status": "source_reconstructed",
        "svg_genuine_vector": True,
        "source_bbox": [clip.x0, clip.y0, clip.x1, clip.y1],
        "vector_primitive_count": sum(path.count("<path ") for path in paths),
        "text_label_count": len(text_elements),
        "visual_comparison": "not_performed",
    }


def create_raster_svg_wrapper(source_path: Path, svg_path: Path) -> dict[str, int | str]:
    """Write a raster-backed SVG wrapper while retaining the original raster."""
    source_path = Path(source_path).resolve()
    svg_path = Path(svg_path).resolve()
    if source_path.parent != svg_path.parent:
        raise ValueError("SVG wrapper and source raster must share a media directory")
    if source_path == svg_path or svg_path.suffix.lower() != ".svg":
        raise ValueError("SVG wrapper must use a separate .svg filename")
    if source_path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
        raise ValueError("SVG wrappers support PNG and JPEG source assets only")
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    with Image.open(source_path) as image:
        image_format = (image.format or "").upper()
        width, height = image.size
        image.verify()
    mime_type = SUPPORTED_RASTER_FORMATS.get(image_format)
    if mime_type is None or width <= 0 or height <= 0:
        raise ValueError("Source asset is not a readable PNG or JPEG image")
    href = html.escape(source_path.name, quote=True)
    svg = (
        f'<svg xmlns="{SVG_NS}" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet" role="img">'
        f'<title>{html.escape(source_path.name)}</title>'
        f'<image x="0" y="0" width="{width}" height="{height}" '
        f'preserveAspectRatio="xMidYMid meet" href="{href}" xlink:href="{href}"/></svg>'
    )
    svg_path.write_text(svg, encoding="utf-8", newline="\n")
    root = ET.parse(svg_path).getroot()
    if root.tag != f"{{{SVG_NS}}}svg":
        svg_path.unlink(missing_ok=True)
        raise ValueError("Generated wrapper is not a valid SVG document")
    return {"filename": svg_path.name, "source_filename": source_path.name,
            "width_px": width, "height_px": height, "media_type": mime_type,
            "representation": "svg_wrapper", "media_format": "svg_raster_wrapper"}


def attach_raster_svg_wrappers(sections: list[dict], media_dir: Path) -> list[str]:
    """Wrap raster-only media; genuine source-vector SVGs are left untouched."""
    media_dir = Path(media_dir)
    wrapped: list[str] = []
    seen: set[str] = set()
    for section in sections:
        for question in section.get("questions", []):
            scopes = [question.get("media", [])]
            scopes.extend(option.get("media", []) for option in question.get("options", []))
            for assets in scopes:
                for asset in assets:
                    filename = asset.get("filename")
                    if asset.get("type") == "math_evidence_source" or asset.get("representation") == "svg_vector":
                        continue
                    if not filename or filename in seen:
                        continue
                    seen.add(filename)
                    source = media_dir / filename
                    if source.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                        continue
                    destination = source.with_name(f"{source.name}.wrapper.svg")
                    try:
                        metadata = create_raster_svg_wrapper(source, destination)
                    except (OSError, ValueError, ET.ParseError):
                        logger.exception("Could not create SVG wrapper for raster media %s", filename)
                        continue
                    asset.update({"svg_filename": metadata["filename"],
                                  "representation": "svg_wrapper",
                                  "media_format": "svg_raster_wrapper",
                                  "svg_generation_status": "raster_wrapper",
                                  "svg_genuine_vector": False})
                    asset.setdefault(
                        "svg_fallback_reason",
                        "An SVG wrapper is provided for browser compatibility, but the original source is raster and has not been vectorized.",
                    )
                    wrapped.append(filename)
    return wrapped
