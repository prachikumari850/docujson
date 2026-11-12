"""Bridge the geometry-based atom/math IR into the active question parser.

The legacy parser remains responsible for question and option boundaries. This
module adds math evidence only when its source bbox belongs unambiguously to a
parsed region; it never rewrites legacy text or moves fragments by proximity.
"""
from __future__ import annotations

import hashlib
import logging
import math
from pathlib import Path

import fitz

from app.config import settings
from app.services.atoms import extract_page_atoms
from app.services.math_units import build_units
from app.services.reading import read_rows

logger = logging.getLogger("docujson")


def page_math_segments(page: fitz.Page, page_number: int, document_fingerprint: str,
                       rawdict: dict, drawings: list[dict], image_infos: list[dict]) -> list[dict]:
    """Build ordered, source-backed text/math segments using the existing IR stages."""
    atoms = extract_page_atoms(
        page,
        page_number,
        document_fingerprint,
        rawdict=rawdict,
        drawings=drawings,
        image_infos=image_infos,
    )
    units = build_units(atoms)
    atom_map = {atom.id: atom for atom in atoms}
    rows = [row.model_dump(mode="json") for row in read_rows(atoms, units)]
    for row in rows:
        for token in row["tokens"]:
            if token["kind"] != "math":
                continue
            token["component_bboxes"] = [
                atom_map[atom_id].source.bbox.model_dump(mode="json")
                for atom_id in token["atom_ids"]
                if atom_id in atom_map and atom_map[atom_id].kind in ("text", "symbol", "rule")
            ]
    return rows


def _regions(source: dict, page_number: int, *, question: bool) -> list[fitz.Rect]:
    regions: list[fitz.Rect] = []
    content_values = list(source.get("content_bboxes", []) or [])
    if not question:
        content_values.extend(source.get("alternate_content_bboxes", []) or [])
    for value in content_values:
        if not question and isinstance(value, dict):
            if value.get("page") != page_number:
                continue
            value = value.get("bbox")
        if question and isinstance(value, dict):
            if value.get("page") != page_number:
                continue
            value = value.get("bbox")
        elif question:
            continue
        elif source.get("page") != page_number:
            continue
        try:
            rect = fitz.Rect(value)
        except (TypeError, ValueError):
            continue
        if not rect.is_empty and all(math.isfinite(value) for value in rect):
            regions.append(rect)
    # The anchor is useful when no continuation line was retained separately.
    if not regions and source.get("page") == page_number and source.get("bbox"):
        try:
            rect = fitz.Rect(source["bbox"])
            if not rect.is_empty and all(math.isfinite(value) for value in rect):
                regions.append(rect)
        except (TypeError, ValueError):
            pass
    return regions


def _coverage(token_box: fitz.Rect, regions: list[fitz.Rect]) -> float:
    if token_box.is_empty or not regions:
        return 0.0
    clipped = [token_box & region for region in regions if not (token_box & region).is_empty]
    if not clipped:
        return 0.0
    # Parser provenance can represent a formula as several character/span
    # boxes. Measure their geometric union so a stacked expression is not
    # rejected simply because no single span covers its whole math bbox.
    xs = sorted({value for rect in clipped for value in (rect.x0, rect.x1)})
    covered = 0.0
    for left, right in zip(xs, xs[1:]):
        if right <= left:
            continue
        middle = (left + right) / 2
        intervals = sorted(
            (rect.y0, rect.y1)
            for rect in clipped
            if rect.x0 <= middle <= rect.x1
        )
        if not intervals:
            continue
        y0, y1 = intervals[0]
        height = 0.0
        for next_y0, next_y1 in intervals[1:]:
            if next_y0 <= y1:
                y1 = max(y1, next_y1)
            else:
                height += y1 - y0
                y0, y1 = next_y0, next_y1
        height += y1 - y0
        covered += (right - left) * height
    return min(1.0, covered / token_box.get_area())


def _ownership_decision(token_box: fitz.Rect, page_number: int, sections: list[dict]):
    options: list[tuple[float, dict, dict]] = []
    questions: list[tuple[float, dict]] = []
    for section in sections:
        for question in section.get("questions", []):
            q_regions = _regions(question.get("source", {}), page_number, question=True)
            q_score = _coverage(token_box, q_regions)
            if q_score:
                questions.append((q_score, question))
            for option in question.get("options", []):
                o_score = _coverage(token_box, _regions(option.get("source", {}), page_number, question=False))
                if o_score:
                    options.append((o_score, question, option))

    options.sort(key=lambda item: item[0], reverse=True)
    questions.sort(key=lambda item: item[0], reverse=True)
    option_candidates = [
        {"question_id": question.get("question_id"), "option_id": option.get("id"), "coverage": round(score, 4)}
        for score, question, option in options[:4]
    ]
    question_candidates = [
        {"question_id": question.get("question_id"), "coverage": round(score, 4)}
        for score, question in questions[:4]
    ]
    if options and options[0][0] >= 0.5:
        best = options[0]
        competing = [item for item in options[1:] if item[0] >= best[0] - 0.05]
        if not competing:
            return (best[1], best[2], "option"), "uniquely_overlaps_option_region", option_candidates, question_candidates
        return None, "overlaps_multiple_option_regions", option_candidates, question_candidates

    # A parser's question content boxes include option lines too. If a math
    # fragment touches any option region, do not fall back to the broad stem box.
    if options and options[0][0] >= 0.15:
        return None, "partial_option_region_overlap", option_candidates, question_candidates
    if not questions or questions[0][0] < 0.72:
        reason = "outside_parsed_question_regions" if not questions else "insufficient_question_region_coverage"
        return None, reason, option_candidates, question_candidates
    if len(questions) > 1 and questions[1][0] >= questions[0][0] - 0.05:
        return None, "overlaps_multiple_question_regions", option_candidates, question_candidates
    return (questions[0][1], None, "question"), "uniquely_overlaps_question_region", option_candidates, question_candidates


def _crop_uncertain(page: fitz.Page, page_number: int, bbox: list[float], atom_ids: list[str],
                    media_dir: Path) -> str | None:
    rect = fitz.Rect(bbox)
    margin = max(1.5, float(settings.media_crop_margin_pt))
    clip = (rect + (-margin, -margin, margin, margin)) & page.rect
    if clip.is_empty:
        return None
    atom_digest = hashlib.sha1("|".join(sorted(atom_ids)).encode("utf-8")).hexdigest()[:12]
    filename = f"math_evidence_p{page_number}_{atom_digest}.png"
    path = media_dir / filename
    if not path.is_file():
        scale = max(1.0, float(settings.math_crop_dpi) / 72.0)
        page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False).save(path)
    return filename


def attach_math_evidence(sections: list[dict], pages: list[dict], source_document: fitz.Document,
                         media_dir: Path) -> dict:
    """Attach validated math tokens to a unique parsed owner; preserve uncertain crops."""
    by_page = {int(page["page"]): page for page in pages}
    assigned = 0
    uncertain = 0
    unassigned = 0
    unassigned_fragments: list[dict] = []
    reason_counts: dict[str, int] = {}
    warnings: list[str] = []
    seen: set[tuple[int, tuple[str, ...]]] = set()
    assigned_atom_owners: dict[str, tuple[str, str | None]] = {}

    for page_number, page_data in by_page.items():
        for row in page_data.get("ordered_segments", []):
            for token in row.get("tokens", []):
                if token.get("kind") == "text":
                    text_bbox = token.get("bbox") or {}
                    text_values = [text_bbox.get(key) for key in ("x0", "y0", "x1", "y1")]
                    if any(value is None for value in text_values):
                        continue
                    text_box = fitz.Rect(text_values)
                    text_owner, _, _, _ = _ownership_decision(text_box, page_number, sections)
                    if text_owner is not None:
                        text_question, text_option, _ = text_owner
                        target = text_option if text_option is not None else text_question
                        atom_ids = list(dict.fromkeys(token.get("atom_ids", [])))
                        segment = {
                            "kind": "text",
                            "text": token.get("text", ""),
                            "source_page": page_number,
                            "source_bbox": text_values,
                            "atom_ids": atom_ids,
                            "math_unit_ids": list(token.get("unit_ids", [])),
                            "reading_column": row.get("column"),
                            "reading_baseline": row.get("baseline"),
                            "status": "extracted",
                        }
                        owned = target.setdefault("ordered_segments", [])
                        if not any(atom_ids and set(atom_ids) == set(existing.get("atom_ids", [])) for existing in owned):
                            owned.append(segment)
                    continue
                if token.get("kind") != "math":
                    continue
                atom_ids = list(dict.fromkeys(token.get("atom_ids", [])))
                identity = (page_number, tuple(atom_ids))
                if not atom_ids:
                    unassigned += 1
                    unassigned_fragments.append({
                        "fragment_id": f"p{page_number}-missing-atoms-{len(unassigned_fragments) + 1}",
                        "page": page_number,
                        "bbox": token.get("bbox"),
                        "raw_text": token.get("text", ""),
                        "atom_ids": [],
                        "math_unit_ids": token.get("unit_ids", []),
                        "reason": "math_token_has_no_atom_ids",
                        "question_candidates": [],
                        "option_candidates": [],
                    })
                    reason_counts["math_token_has_no_atom_ids"] = reason_counts.get("math_token_has_no_atom_ids", 0) + 1
                    continue
                if identity in seen:
                    continue
                seen.add(identity)
                bbox = token.get("bbox", {})
                values = [bbox.get(key) for key in ("x0", "y0", "x1", "y1")]
                if any(value is None for value in values):
                    unassigned += 1
                    reason = "math_token_bbox_missing_coordinates"
                    reason_counts[reason] = reason_counts.get(reason, 0) + 1
                    unassigned_fragments.append({
                        "fragment_id": f"p{page_number}-{hashlib.sha1('|'.join(atom_ids).encode()).hexdigest()[:12]}",
                        "page": page_number, "bbox": bbox, "raw_text": token.get("text", ""),
                        "atom_ids": atom_ids, "math_unit_ids": token.get("unit_ids", []), "latex_candidate": token.get("latex"), "reason": reason,
                        "question_candidates": [], "option_candidates": [],
                    })
                    continue
                token_box = fitz.Rect(values)
                owner, reason, option_candidates, question_candidates = _ownership_decision(token_box, page_number, sections)
                row_context = {"column": row.get("column"), "baseline": row.get("baseline")}
                atom_conflicts = [atom_id for atom_id in atom_ids if atom_id in assigned_atom_owners]
                if owner is not None and atom_conflicts:
                    owner = None
                    reason = "atom_ids_already_owned"
                if owner is None:
                    unassigned += 1
                    reason_counts[reason] = reason_counts.get(reason, 0) + 1
                    unassigned_fragments.append({
                        "fragment_id": f"p{page_number}-{hashlib.sha1('|'.join(atom_ids).encode()).hexdigest()[:12]}",
                        "page": page_number,
                        "bbox": values,
                        "raw_text": token.get("text", ""),
                        "latex_candidate": token.get("latex"),
                        "math_unit_ids": token.get("unit_ids", []),
                        "status": token.get("status"),
                        "atom_ids": atom_ids,
                        "node": token.get("node"),
                        "reading_row": row_context,
                        "conflicting_atom_owners": {
                            atom_id: {
                                "question_id": assigned_atom_owners[atom_id][0],
                                "option_id": assigned_atom_owners[atom_id][1],
                            }
                            for atom_id in atom_conflicts
                        },
                        "reason": reason,
                        "question_candidates": question_candidates,
                        "option_candidates": option_candidates,
                    })
                    continue

                question, option, scope = owner
                confirmed = token.get("status") == "confirmed" and bool(token.get("latex"))
                token_reasons = list(token.get("reasons", []))
                crop_filename = None
                if not confirmed:
                    token_reasons.append("Geometry-based math reconstruction is uncertain; inspect the retained source crop.")
                    crop_filename = _crop_uncertain(
                        source_document[page_number - 1], page_number, values, atom_ids, media_dir
                    )
                    uncertain += 1

                atom_boxes = [
                    [box[key] for key in ("x0", "y0", "x1", "y1")]
                    for box in token.get("component_bboxes", [])
                ]
                evidence = {
                    "original_text": token.get("text", ""),
                    "reconstructed_text": token.get("text", "") if confirmed else None,
                    "normalized_text": None,
                    "latex": token.get("latex") if confirmed else None,
                    "mathml": None,
                    "source_page": page_number,
                    "source_bbox": values,
                    "component_bboxes": atom_boxes,
                    "extraction_method": "pymupdf_geometry_ir",
                    "atom_ids": atom_ids,
                    "math_unit_ids": list(token.get("unit_ids", [])),
                    "source_crop_filename": crop_filename,
                    "confidence": None,
                    "review_required": not confirmed,
                    "review_reasons": list(dict.fromkeys(token_reasons)),
                }
                target = option if scope == "option" else question
                target.setdefault("math_evidence", []).append(evidence)
                target.setdefault("ordered_segments", []).append({
                    "kind": "math",
                    "text": token.get("text", ""),
                    "latex": token.get("latex") if confirmed else None,
                    "source_page": page_number,
                    "source_bbox": values,
                    "atom_ids": atom_ids,
                    "math_unit_ids": list(token.get("unit_ids", [])),
                    "reading_column": row.get("column"),
                    "reading_baseline": row.get("baseline"),
                    "status": "confirmed" if confirmed else "review_required",
                    "review_reasons": list(dict.fromkeys(token_reasons)),
                })
                for atom_id in atom_ids:
                    assigned_atom_owners[atom_id] = (question["question_id"], option.get("id") if option else None)
                assigned += 1

    if uncertain:
        warnings.append(f"{uncertain} geometry-derived mathematical fragments remain uncertain; source crops were retained.")
    if unassigned:
        warnings.append(f"{unassigned} geometry-derived mathematical fragments could not be assigned unambiguously and were not attached to questions or options.")
    logger.info("Math IR integration: assigned=%d uncertain=%d unassigned=%d", assigned, uncertain, unassigned)
    return {
        "assigned": assigned,
        "uncertain": uncertain,
        "unassigned": unassigned,
        "unassigned_reasons": reason_counts,
        "unassigned_fragments": unassigned_fragments,
        "warnings": warnings,
    }


def validate_segmentation(sections: list[dict], overlap_tolerance: float = 0.02) -> list[dict]:
    """Check parser identities and option-region ownership invariants.

    This validation does not try to repair ownership. It reports overlap and ID
    defects so the original geometry stays reviewable.
    """
    issues: list[dict] = []
    question_ids: dict[str, dict] = {}
    question_regions: list[tuple[dict, int, fitz.Rect]] = []
    option_regions: list[tuple[dict, dict, int, fitz.Rect]] = []

    for section in sections:
        for question in section.get("questions", []):
            question_id = str(question.get("question_id", ""))
            if question_id in question_ids:
                issues.append({
                    "code": "duplicate_question_id",
                    "question_id": question_id,
                    "question_number": question.get("question_number"),
                    "message": "Question ID is not unique across the document.",
                })
            question_ids[question_id] = question

            for option_index, option in enumerate(question.get("options", [])):
                for other in question.get("options", [])[:option_index]:
                    if str(option.get("id")) == str(other.get("id")):
                        issues.append({
                            "code": "duplicate_option_id",
                            "question_id": question_id,
                            "question_number": question.get("question_number"),
                            "option_id": option.get("id"),
                            "message": "Option ID is duplicated within its question.",
                        })
                        break
                source = option.get("source", {})
                page_number = source.get("page")
                for rect in _regions(source, page_number, question=False) if page_number else []:
                    option_regions.append((question, option, page_number, rect))

            source = question.get("source", {})
            for region in source.get("content_bboxes", []) or []:
                if not isinstance(region, dict) or not region.get("page") or not region.get("bbox"):
                    continue
                try:
                    rect = fitz.Rect(region["bbox"])
                except (TypeError, ValueError):
                    continue
                if not rect.is_empty:
                    question_regions.append((question, int(region["page"]), rect))

    def overlap_ratio(a: fitz.Rect, b: fitz.Rect) -> float:
        smaller = min(a.get_area(), b.get_area())
        return (a & b).get_area() / smaller if smaller > 0 else 0.0

    for index, (question, option, page_number, rect) in enumerate(option_regions):
        for other_question, other_option, other_page, other_rect in option_regions[index + 1:]:
            if page_number != other_page or question is not other_question or option is other_option:
                continue
            if overlap_ratio(rect, other_rect) > overlap_tolerance:
                issues.append({
                    "code": "overlapping_option_regions",
                    "question_id": question.get("question_id"),
                    "question_number": question.get("question_number"),
                    "option_ids": [option.get("id"), other_option.get("id")],
                    "page": page_number,
                    "bbox": list(rect & other_rect),
                    "message": "Distinct options have overlapping content regions; math and media ownership needs review.",
                })

    by_page: dict[int, list[tuple[dict, fitz.Rect]]] = {}
    for question, page_number, rect in question_regions:
        by_page.setdefault(page_number, []).append((question, rect))
    for page_number, regions in by_page.items():
        ordered = sorted(regions, key=lambda item: (item[1].y0, item[1].x0))
        for index, (question, rect) in enumerate(ordered):
            for other_question, other_rect in ordered[index + 1:]:
                if other_rect.y0 >= rect.y1:
                    break
                if question is other_question:
                    continue
                if overlap_ratio(rect, other_rect) > 0.1:
                    issues.append({
                        "code": "overlapping_question_regions",
                        "question_ids": [question.get("question_id"), other_question.get("question_id")],
                        "question_numbers": [question.get("question_number"), other_question.get("question_number")],
                        "page": page_number,
                        "bbox": list(rect & other_rect),
                        "message": "Distinct question source regions overlap; possible cross-question ownership requires review.",
                    })
    return issues
