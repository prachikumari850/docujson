"""Shared real-document fixtures for extraction regression tests.

Set DOCUJSON_PHYSICS_QP_PDF to override the preserved SRG source path. Set
DOCUJSON_REGRESSION=1 in CI/regression runs to turn an unavailable fixture into
a clear test failure instead of a skip.
"""
from __future__ import annotations

import os
from pathlib import Path

import fitz
import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _is_srg_physics_source(path: Path) -> bool:
    try:
        with fitz.open(path) as document:
            if len(document) != 16:
                return False
            page_text = [" ".join(document[index].get_text().split()) for index in (2, 3, 4)]
        joined = " ".join(page_text)
        return all(token in joined for token in (
            "SECTION - A (PHYSICS)",
            "Differentiation of x",
            "Resultant of three non-coplanar",
            "A vector makes 45",
        ))
    except (OSError, RuntimeError, ValueError):
        return False


def _source_candidates() -> list[Path]:
    configured = os.getenv("DOCUJSON_PHYSICS_QP_PDF")
    if configured:
        return [Path(configured).expanduser()]

    candidates = [
        PROJECT_ROOT / "backend" / "tests" / "fixtures" / "physics_qp.pdf",
        *sorted((PROJECT_ROOT / "storage" / ".audit-real-current").glob("**/input_0.pdf")),
    ]
    return candidates


@pytest.fixture(scope="session")
def physics_qp_pdf() -> Path:
    candidates = _source_candidates()
    for candidate in candidates:
        if candidate.is_file() and _is_srg_physics_source(candidate):
            return candidate.resolve()

    configured = os.getenv("DOCUJSON_PHYSICS_QP_PDF")
    if configured:
        detail = f"Configured source {configured!r} is missing or is not the expected 16-page SRG Physics paper."
    else:
        detail = "No matching source was found in tests/fixtures or preserved storage/.audit-real-current."
    message = (
        "Real-document extraction regression fixture unavailable: " + detail + " "
        "Provide the original SRG Physics PDF with DOCUJSON_PHYSICS_QP_PDF."
    )
    if os.getenv("DOCUJSON_REGRESSION", "").strip().lower() in {"1", "true", "yes"}:
        pytest.fail(message, pytrace=False)
    pytest.skip(message)


@pytest.fixture(scope="session")
def physics_qp_doc(physics_qp_pdf):
    with fitz.open(physics_qp_pdf) as document:
        yield document
