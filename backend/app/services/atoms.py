"""Stage 1 - read one PDF page into atoms.

Atoms are the raw facts: every visible character, Type3 symbol glyph, thin
horizontal rule (fraction bars, radical overbars), image and other drawing,
each with an exact bounding box.  Nothing is merged, guessed or reordered here.
"""
from __future__ import annotations

import fitz  # PyMuPDF

from app.ir import Atom, BBox, SourceRef, atom_id

RULE_MAX_THICKNESS = 1.5     # pt: filled/stroked rectangles thinner than this are "rules"
RULE_MIN_LENGTH = 3.0        # pt


def column_of(b: BBox, page_width: float) -> str:
    """Two-column hint for ALLEN-style papers.  Phase 6 replaces this with real column detection."""
    mid = page_width / 2
    if b.x0 < mid - 15 and b.x1 > mid + 15:
        return "full"
    return "left" if (b.x0 + b.x1) / 2 < mid else "right"


def _box(rect) -> BBox:
    x0, y0, x1, y1 = (float(v) for v in rect)
    return BBox(x0=x0, y0=y0, x1=max(x1, x0), y1=max(y1, y0))


def _type3_box(bbox: BBox, origin: tuple[float, float], size: float) -> tuple[BBox, bool]:
    """PyMuPDF derives a Type3 glyph's box from the font's FontBBox, which many PDFs get wrong
    (e.g. an arrow reported 40 pt above where it is drawn).  The origin is reliable, so when the
    box does not sit on the origin we rebuild a plausible band around it and mark it ``derived``."""
    ox, oy = origin
    if bbox.y1 >= oy - 0.3 * size and bbox.y0 >= oy - 1.5 * size:
        return bbox, False
    return BBox(x0=bbox.x0, y0=oy - size, x1=bbox.x1, y1=oy + 0.25 * size), True


def extract_page_atoms(
    page: "fitz.Page",
    page_no: int,
    doc_fp: str,
    *,
    rawdict: dict | None = None,
    drawings: list[dict] | None = None,
    image_infos: list[dict] | None = None,
) -> list[Atom]:
    """Extract page atoms, optionally reusing geometry already read by the caller.

    ``page_no`` is 1-based. The optional inputs let the active PDF extractor
    share its structured page reads rather than asking PyMuPDF to decode them
    a second time.
    """
    width = page.rect.width
    atoms: list[Atom] = []
    used: set[str] = set()
    rawdict = rawdict if rawdict is not None else page.get_text("rawdict")
    drawings = drawings if drawings is not None else page.get_drawings()
    image_infos = image_infos if image_infos is not None else page.get_image_info()

    def add(kind, bbox: BBox, **kw) -> None:
        aid = atom_id(doc_fp, page_no, bbox, kw.get("text"))
        n = 1
        while aid in used:                       # identical glyph at identical place
            n += 1
            aid = f"{atom_id(doc_fp, page_no, bbox, kw.get('text'))}-{n}"
        used.add(aid)
        atoms.append(Atom(id=aid, kind=kind,
                          source=SourceRef(page=page_no, bbox=bbox, column=column_of(bbox, width)), **kw))

    line_no = -1
    for block in rawdict.get("blocks", []):
        for line in block.get("lines", []):
            line_no += 1
            for span in line["spans"]:
                type3 = span["font"].startswith("Type3")
                for ch in span["chars"]:
                    if not ch["c"].strip():          # spaces / nbsp carry no geometry we need
                        continue
                    box, derived = _box(ch["bbox"]), False
                    origin = (float(ch["origin"][0]), float(ch["origin"][1]))
                    if type3:
                        box, derived = _type3_box(box, origin, float(span["size"]))
                    add("symbol" if type3 else "text", box, text=ch["c"], font=span["font"],
                        size=round(span["size"], 2), type3=type3, line=line_no, origin=origin,
                        geometry="derived" if derived else "exact")

    for d in drawings:
        r = d["rect"]
        w, h = r.width, r.height
        if h <= RULE_MAX_THICKNESS and w >= RULE_MIN_LENGTH:
            add("rule", _box(r))
        elif w > 0.3 or h > 0.3:
            add("drawing", _box(r))

    for info in image_infos:
        add("image", _box(info["bbox"]))
    return atoms
