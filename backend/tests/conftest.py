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
from app import database

import mongomock
from app.database_indexes import ensure_indexes


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

@pytest.fixture(autouse=True)
def mock_mongodb_for_api_tests(request, monkeypatch):
    if request.path.name == "test_database_connection.py":
        yield
        return

    original_client = database.mongo_client
    original_database = database.mongo_database

    mongo_client = mongomock.MongoClient()
    mongo_database = mongo_client["neetday_test"]

    ensure_indexes(mongo_database)

    def mock_connect():
        database.mongo_client = mongo_client
        database.mongo_database = mongo_database
        return mongo_database

    def mock_close():
        database.mongo_client = None
        database.mongo_database = None

    monkeypatch.setattr(database, "connect_to_mongo", mock_connect)
    monkeypatch.setattr(database, "close_mongo_connection", mock_close)

    mock_connect()

    try:
        yield
    finally:
        database.mongo_client = original_client
        database.mongo_database = original_database
        mongo_client.close()

@pytest.fixture(autouse=True)
def authenticate_legacy_upload_regression_tests(request, monkeypatch):
    if request.path.name not in {
        "test_mcq_classification.py",
        "test_srg_source_regression.py",
    }:
        return

    from app.main import app
    from app.dependencies.auth import (
        AuthenticatedPrincipal,
        get_current_principal,
    )
    from app.dependencies.security import require_csrf

    principal = AuthenticatedPrincipal(
        user_id="test-user-123",
        organization_id="test-org-123",
        role="owner",
    )

    monkeypatch.setitem(
        app.dependency_overrides,
        get_current_principal,
        lambda: principal,
    )

    monkeypatch.setitem(
        app.dependency_overrides,
        require_csrf,
        lambda: None,
    )