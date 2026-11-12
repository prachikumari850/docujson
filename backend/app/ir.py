"""DocuJSON intermediate representation (IR).

Single source of truth for the HTML preview, the JSON export, media references
and validation.  Nothing in here parses PDFs or renders anything: extraction
stages build an ``ExtractedDocument``; every consumer reads it.

Coordinates: PDF points, origin top-left (PyMuPDF convention), pages 1-based.
"""
from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "2.0"
Lang = Literal["en", "hi", "mixed"]


# --------------------------------------------------------------------------- #
# Geometry and provenance
# --------------------------------------------------------------------------- #
class BBox(BaseModel):
    model_config = ConfigDict(frozen=True)
    x0: float
    y0: float
    x1: float
    y1: float

    @model_validator(mode="after")
    def _ordered(self) -> "BBox":
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError(f"inverted bbox {self.x0, self.y0, self.x1, self.y1}")
        return self

    @property
    def area(self) -> float:
        return (self.x1 - self.x0) * (self.y1 - self.y0)

    def union(self, o: "BBox") -> "BBox":
        return BBox(x0=min(self.x0, o.x0), y0=min(self.y0, o.y0),
                    x1=max(self.x1, o.x1), y1=max(self.y1, o.y1))

    def intersection_area(self, o: "BBox") -> float:
        w = min(self.x1, o.x1) - max(self.x0, o.x0)
        h = min(self.y1, o.y1) - max(self.y0, o.y0)
        return w * h if w > 0 and h > 0 else 0.0

    def overlap_ratio(self, o: "BBox") -> float:
        """Intersection area divided by the smaller box's area."""
        small = min(self.area, o.area)
        return self.intersection_area(o) / small if small > 0 else 0.0

    @staticmethod
    def union_all(boxes: list["BBox"]) -> "BBox":
        out = boxes[0]
        for b in boxes[1:]:
            out = out.union(b)
        return out


class SourceRef(BaseModel):
    """Where a thing came from in the source document."""
    model_config = ConfigDict(frozen=True)
    page: int = Field(ge=1)
    bbox: BBox
    column: Literal["left", "right", "full"] | None = None


# --------------------------------------------------------------------------- #
# Atoms: the smallest facts read from the PDF.  Never invented, never merged.
# --------------------------------------------------------------------------- #
AtomKind = Literal["text", "symbol", "rule", "image", "drawing"]


class Atom(BaseModel):
    id: str
    kind: AtomKind
    source: SourceRef
    text: str | None = None          # exact extracted characters, untouched
    font: str | None = None
    size: float | None = None
    type3: bool = False              # Type3 glyphs carry unreliable text mapping
    line: int | None = None          # PDF text-line index on the page (stream order)
    origin: tuple[float, float] | None = None   # glyph origin (x, baseline y) as reported by the PDF
    geometry: Literal["exact", "derived"] = "exact"   # "derived": bbox rebuilt from origin (Type3 metrics wrong)
    note: str | None = None          # e.g. "arrow above letter"


# --------------------------------------------------------------------------- #
# Mathematics: a semantic tree built from geometry, rendered separately.
# --------------------------------------------------------------------------- #
MathOp = Literal[
    "text", "num", "var", "sym", "group", "frac", "sup", "sub", "subsup",
    "sqrt", "vec", "hat", "integral", "limit", "func", "matrix", "unresolved",
]


class MathNode(BaseModel):
    op: MathOp
    value: str | None = None                       # leaf payload (exact glyph text)
    children: list["MathNode"] = Field(default_factory=list)
    atom_ids: list[str] = Field(default_factory=list)   # evidence for this node


MathNode.model_rebuild()

MathStatus = Literal["confirmed", "uncertain", "unresolved"]


class MathExpression(BaseModel):
    id: str
    status: MathStatus
    raw_text: str                                  # what extraction literally saw
    tree: MathNode | None = None                   # reconstructed semantics
    latex: str | None = None                       # derived from tree, never from OCR
    source: SourceRef
    atom_ids: list[str] = Field(default_factory=list)
    crop_asset_id: str | None = None               # evidence crop (mandatory if not confirmed)
    review_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _honest(self) -> "MathExpression":
        if self.latex is not None and (self.status != "confirmed" or self.tree is None):
            raise ValueError("latex is only allowed for a confirmed expression with a tree")
        if self.status != "confirmed" and not self.crop_asset_id:
            raise ValueError("an uncertain/unresolved expression must carry a source crop")
        return self


# --------------------------------------------------------------------------- #
# Media
# --------------------------------------------------------------------------- #
MediaKind = Literal["figure", "graph", "diagram", "option_image", "table_crop", "math_crop"]
Representation = Literal["raster", "svg_wrapper", "svg_vector"]


class MediaAsset(BaseModel):
    id: str
    kind: MediaKind
    source: SourceRef
    representation: Representation = "raster"
    raster_file: str | None = None                 # path inside the export package
    svg_file: str | None = None
    width_px: int | None = None
    height_px: int | None = None
    sha256: str | None = None
    vector_verified: bool = False                  # True only after comparison with the original
    atom_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _has_file(self) -> "MediaAsset":
        if not (self.raster_file or self.svg_file):
            raise ValueError("media asset needs a raster or svg file")
        if self.representation == "svg_vector" and not self.vector_verified:
            raise ValueError("svg_vector must be verified against the original raster")
        if self.representation == "svg_vector" and not self.raster_file:
            raise ValueError("keep the original raster as source evidence")
        return self


class TableBlock(BaseModel):
    id: str
    source: SourceRef
    rows: list[list[str]] | None = None            # only when the grid is unambiguous
    crop_asset_id: str | None = None               # fallback / evidence
    atom_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _either(self) -> "TableBlock":
        if self.rows is None and not self.crop_asset_id:
            raise ValueError("table needs rows or a crop")
        return self


# --------------------------------------------------------------------------- #
# Content: ordered segments, so inline math keeps its place in the sentence.
# --------------------------------------------------------------------------- #
class Segment(BaseModel):
    kind: Literal["text", "math", "media", "table"]
    text: str | None = None
    lang: Lang | None = None
    ref_id: str | None = None                      # math / media / table id

    @model_validator(mode="after")
    def _shape(self) -> "Segment":
        if self.kind == "text" and self.text is None:
            raise ValueError("text segment needs text")
        if self.kind != "text" and not self.ref_id:
            raise ValueError(f"{self.kind} segment needs ref_id")
        return self


class Content(BaseModel):
    en: list[Segment] = Field(default_factory=list)
    hi: list[Segment] = Field(default_factory=list)

    def all_segments(self) -> list[Segment]:
        return [*self.en, *self.hi]


# --------------------------------------------------------------------------- #
# Questions
# --------------------------------------------------------------------------- #
class Option(BaseModel):
    id: str
    label: str                                     # "1", "2", "A" ... exactly as printed
    content: Content = Field(default_factory=Content)
    source: SourceRef                              # union of ITS OWN atoms only
    atom_ids: list[str] = Field(default_factory=list)


AnswerProvenance = Literal["source_marked", "answer_key_matched", "answer_key_uncertain", "unavailable"]


class Answer(BaseModel):
    value: str | None = None                       # an option label
    provenance: AnswerProvenance = "unavailable"
    evidence: SourceRef | None = None

    @model_validator(mode="after")
    def _consistent(self) -> "Answer":
        has = self.value is not None
        if has and self.provenance in ("unavailable", "answer_key_uncertain"):
            raise ValueError("a stated answer needs a confirmed provenance")
        if not has and self.provenance in ("source_marked", "answer_key_matched"):
            raise ValueError("confirmed provenance needs a value")
        return self


class Validation(BaseModel):
    status: Literal["valid", "needs_review", "excluded"] = "needs_review"
    reasons: list[str] = Field(default_factory=list)


class Question(BaseModel):
    id: str
    number: int
    section: str | None = None
    regions: list[SourceRef]                       # one per page the question spans
    stem: Content = Field(default_factory=Content)
    options: list[Option] = Field(default_factory=list)
    media_ids: list[str] = Field(default_factory=list)   # stem-level figures/graphs
    answer: Answer = Field(default_factory=Answer)
    atom_ids: list[str] = Field(default_factory=list)
    validation: Validation = Field(default_factory=Validation)


class Excluded(BaseModel):
    """Material deliberately kept out of the MCQ export, with the rule that excluded it."""
    source: SourceRef
    rule: str
    text_preview: str | None = None
    atom_ids: list[str] = Field(default_factory=list)


class DocumentMeta(BaseModel):
    title: str
    source_filename: str
    source_sha256: str
    total_pages: int
    languages: list[str] = Field(default_factory=list)
    answer_key_provided: bool = False


class ExtractedDocument(BaseModel):
    schema_version: str = SCHEMA_VERSION
    meta: DocumentMeta
    atoms: dict[str, Atom] = Field(default_factory=dict)
    math: dict[str, MathExpression] = Field(default_factory=dict)
    media: dict[str, MediaAsset] = Field(default_factory=dict)
    tables: dict[str, TableBlock] = Field(default_factory=dict)
    questions: list[Question] = Field(default_factory=list)
    unassigned_atom_ids: list[str] = Field(default_factory=list)
    excluded: list[Excluded] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Stable ids: same input bytes + same geometry => same ids on every run.
# --------------------------------------------------------------------------- #
def doc_fingerprint(pdf_bytes: bytes) -> str:
    return hashlib.sha256(pdf_bytes).hexdigest()[:12]


def question_id(doc_fp: str, number: int, section: str | None = None) -> str:
    sec = (section or "x").lower().replace(" ", "")
    return f"{doc_fp}-{sec}-q{number:03d}"


def child_id(parent_id: str, kind: str, index: int) -> str:
    return f"{parent_id}-{kind}{index}"


def atom_id(doc_fp: str, page: int, bbox: BBox, text: str | None) -> str:
    key = f"{page}|{bbox.x0:.1f},{bbox.y0:.1f},{bbox.x1:.1f},{bbox.y1:.1f}|{text or ''}"
    return f"a{page:02d}-" + hashlib.sha1((doc_fp + key).encode("utf8")).hexdigest()[:10]


# --------------------------------------------------------------------------- #
# Plain text and the semantic digest used by preview/JSON consistency checks.
# --------------------------------------------------------------------------- #
def plain_text(segments: list[Segment], doc: ExtractedDocument) -> str:
    parts: list[str] = []
    for s in segments:
        if s.kind == "text":
            parts.append(s.text or "")
        elif s.kind == "math":
            m = doc.math.get(s.ref_id or "")
            parts.append((m.latex or m.raw_text) if m else "")
        else:
            parts.append(f"[{s.kind}:{s.ref_id}]")
    return " ".join(p.strip() for p in parts if p.strip())


def semantic_digest(q: Question, doc: ExtractedDocument) -> dict:
    """Canonical, renderer-independent summary of one question.

    The preview payload and the JSON exporter must both be reducible to this
    exact structure; tests compare the two (Phase 9)."""
    def refs(segs: list[Segment], kind: str) -> list[str]:
        return sorted(s.ref_id for s in segs if s.kind == kind and s.ref_id)

    segs = q.stem.all_segments()
    return {
        "id": q.id,
        "number": q.number,
        "stem_en": plain_text(q.stem.en, doc),
        "stem_hi": plain_text(q.stem.hi, doc),
        "options": [
            {"label": o.label, "en": plain_text(o.content.en, doc),
             "hi": plain_text(o.content.hi, doc),
             "math": refs(o.content.all_segments(), "math"),
             "media": refs(o.content.all_segments(), "media")}
            for o in q.options
        ],
        "math": refs(segs, "math"),
        "media": sorted({*q.media_ids, *refs(segs, "media")}),
        "answer": (q.answer.value, q.answer.provenance),
    }


# --------------------------------------------------------------------------- #
# Invariants: what "never mix two questions" means as checkable rules.
# --------------------------------------------------------------------------- #
class Issue(BaseModel):
    level: Literal["error", "warning"]
    code: str
    where: str
    message: str


OVERLAP_TOLERANCE = 0.02   # fraction of the smaller box allowed to overlap


def validate_document(doc: ExtractedDocument) -> list[Issue]:
    issues: list[Issue] = []

    def err(code: str, where: str, msg: str) -> None:
        issues.append(Issue(level="error", code=code, where=where, message=msg))

    def warn(code: str, where: str, msg: str) -> None:
        issues.append(Issue(level="warning", code=code, where=where, message=msg))

    # 1. unique ids across every addressable object
    seen: dict[str, str] = {}
    def claim(i: str, where: str) -> None:
        if i in seen:
            err("duplicate_id", where, f"id {i!r} also used by {seen[i]}")
        seen[i] = where
    for q in doc.questions:
        claim(q.id, f"question {q.number}")
        for o in q.options:
            claim(o.id, f"question {q.number} option {o.label}")
    for k in (*doc.math, *doc.media, *doc.tables):
        claim(k, "asset")

    # 2. every atom belongs to exactly one question, or is explicitly unassigned
    owner: dict[str, str] = {}
    for q in doc.questions:
        for a in q.atom_ids:
            if a not in doc.atoms:
                err("unknown_atom", f"question {q.number}", f"atom {a} is not in the atom table")
            if a in owner and owner[a] != q.id:
                err("atom_in_two_questions", f"question {q.number}",
                    f"atom {a} also belongs to {owner[a]}")
            owner[a] = q.id
    for a in doc.unassigned_atom_ids:
        if a in owner:
            err("atom_assigned_and_unassigned", a, f"atom is owned by {owner[a]}")

    # 3. per-question structure
    for q in doc.questions:
        w = f"question {q.number}"
        labels = [o.label for o in q.options]
        if len(labels) != len(set(labels)):
            err("duplicate_option_label", w, f"labels {labels}")
        if q.validation.status != "excluded" and len(q.options) < 2:
            err("not_an_mcq", w, "fewer than two options; exclude it or mark unresolved")
        if q.answer.value is not None and q.answer.value not in labels:
            err("answer_not_an_option", w, f"answer {q.answer.value!r} not in {labels}")
        q_atoms = set(q.atom_ids)
        for o in q.options:
            stray = [a for a in o.atom_ids if a not in q_atoms]
            if stray:
                err("option_atom_outside_question", f"{w} option {o.label}", f"{stray[:3]}")
        # options of one question must not overlap each other on the page
        for i, a in enumerate(q.options):
            for b in q.options[i + 1:]:
                if a.source.page == b.source.page and \
                   a.source.bbox.overlap_ratio(b.source.bbox) > OVERLAP_TOLERANCE:
                    err("options_overlap", w, f"options {a.label} and {b.label} share page area")

        # 4. every reference resolves
        for s in [*q.stem.all_segments(), *(s for o in q.options for s in o.content.all_segments())]:
            table = {"math": doc.math, "media": doc.media, "table": doc.tables}.get(s.kind)
            if table is not None and s.ref_id not in table:
                err("dangling_reference", w, f"{s.kind} {s.ref_id} does not exist")
        for m in q.media_ids:
            if m not in doc.media:
                err("dangling_reference", w, f"media {m} does not exist")

    # 5. question regions must not overlap other questions on the same page/column
    for i, a in enumerate(doc.questions):
        for b in doc.questions[i + 1:]:
            for ra in a.regions:
                for rb in b.regions:
                    if ra.page == rb.page and ra.column == rb.column and \
                       ra.bbox.overlap_ratio(rb.bbox) > OVERLAP_TOLERANCE:
                        err("question_regions_overlap", f"questions {a.number}/{b.number}",
                            f"page {ra.page} column {ra.column}")

    # 6. uncertain math must be visible, never silent
    for m in doc.math.values():
        if m.status != "confirmed" and not m.review_reasons:
            warn("math_without_reason", m.id, "uncertain math has no review reason")
    return issues