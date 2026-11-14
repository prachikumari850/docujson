from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field
import json
import logging
import re
import shutil
import zipfile
from pathlib import Path

from contextlib import asynccontextmanager

from app import database
from app.routers.auth import router as auth_router

from app.dependencies.auth import (
    AuthenticatedPrincipal,
    get_current_principal,
)

import httpx
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
    Query,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import settings
from app.storage import (
    create_job,
    job_dir,
    read_job,
    update_job,
    list_jobs,
    save_review_decision,
    save_answer_key_decision,
    create_publication,
    list_publications,
    read_publication,
    get_analytics_overview,
    read_job_for_organization,
    job_dir_for_organization,
    delete_job
)
from app.services.engine import run_conversion
from app.dependencies.security import require_csrf


logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("docujson")

@asynccontextmanager
async def lifespan(app: FastAPI):
    database.connect_to_mongo()

    try:
        yield
    finally:
        database.close_mongo_connection()

app = FastAPI(
    title="DocuJSON API",
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(auth_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".txt",
}

class ReviewDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = Field(default=None, max_length=2000)

class AnswerKeyDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    corrected_answer: str | None = Field(default=None, max_length=50)
    note: str | None = Field(default=None, max_length=2000)

@app.get("/api/health")
async def health():
    available = False

    if settings.ollama_enabled:
        try:
            async with httpx.AsyncClient(
                timeout=3,
            ) as client:
                response = await client.get(
                    settings.ollama_base_url.rstrip("/")
                    + "/api/tags"
                )

                response.raise_for_status()

                models = response.json().get(
                    "models",
                    [],
                )

                available = any(model.get("name") == settings.ollama_model for model in models)

        except Exception:
            available = False

    return {
        "status": "ok",
        "ollama": {
            "enabled": settings.ollama_enabled,
            "available": available,
            "model": (
                settings.ollama_model
                if settings.ollama_enabled
                else None
            ),
        },
    }

@app.get("/api/settings")
async def get_settings():
    return {
        "upload": {
            "max_size_mb": settings.max_upload_mb,
            "supported_formats": sorted(
                extension.lstrip(".")
                for extension in ALLOWED_EXTENSIONS
            ),
        },
        "storage": {
            "type": "local",
        },
        "ocr": {
            "languages": settings.ocr_languages,
            "dpi": settings.ocr_dpi,
        },
        "extraction": {
            "media_crop_margin_pt": settings.media_crop_margin_pt,
            "math_crop_dpi": settings.math_crop_dpi,
        },
        "ai": {
            "provider": "ollama",
            "enabled": settings.ollama_enabled,
            "model": (
                settings.ollama_model
                if settings.ollama_enabled
                else None
            ),
        },
    }

@app.get("/api/analytics/overview")
async def analytics_overview(
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
):
    return get_analytics_overview(
        organization_id=principal.organization_id
    )

@app.get("/api/documents")
async def list_documents(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
):
    jobs, total = list_jobs(
        limit=limit,
        offset=offset,
        organization_id=principal.organization_id,
    )

    documents = []

    for job in jobs:
        result = job.get("result") or {}
        document = result.get("document") or {}

        documents.append(
        {
            "conversion_id": job.get("conversion_id"),
            "status": job.get("status"),
            "progress": job.get("progress", 0),
            "stage": job.get("stage", ""),
            "error": job.get("error"),
            "filename": document.get("source_filename") or job.get("filename"),
            "format": document.get("source_format") or job.get("format"),
            "total_questions": document.get("total_questions"),
            "total_pages": document.get("total_pages"),
        }
    )

    return {
        "items": documents,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/questions")
async def list_questions(
    search: str | None = Query(default=None, max_length=200),
    question_type: str | None = Query(default=None, max_length=50),
    review_required: bool | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
):
    jobs, _ = list_jobs(
        limit=10000,
        offset=0,
        organization_id=principal.organization_id,
    )

    questions = []
    normalized_search = search.strip().casefold() if search else None
    normalized_type = question_type.strip().casefold() if question_type else None

    for job in jobs:
        if job.get("status") != "completed":
            continue

        result = job.get("result") or {}
        document = result.get("document") or {}
        filename = document.get("source_filename") or job.get("filename")

        for section in result.get("sections") or []:
            section_name = section.get("section_name")

            for question in section.get("questions") or []:
                question_text = question.get("question") or {}
                searchable_text = " ".join(
                    str(value)
                    for value in (
                        question_text.get("en"),
                        question_text.get("hi"),
                        question.get("question_number"),
                    )
                    if value is not None
                ).casefold()

                if normalized_search and normalized_search not in searchable_text:
                    continue

                if (
                    normalized_type
                    and str(question.get("question_type", "")).casefold()
                    != normalized_type
                ):
                    continue

                if (
                    review_required is not None
                    and question.get("review_required", False) != review_required
                ):
                    continue

                questions.append(
                    {
                        **question,
                        "section_name": section_name,
                        "conversion_id": job.get("conversion_id"),
                        "source_filename": filename,
                    }
                )

    total = len(questions)

    return {
        "items": questions[offset:offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@app.get("/api/review/questions")
async def list_review_questions(
    search: str | None = Query(default=None, max_length=200),
    decision: Literal["pending", "approved", "rejected"] = "pending",
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
):
    jobs, _ = list_jobs(
        limit=10000,
        offset=0,
        organization_id=principal.organization_id,
    )

    questions = []
    normalized_search = search.strip().casefold() if search else None

    for job in jobs:
        if job.get("status") != "completed":
            continue

        result = job.get("result") or {}
        document = result.get("document") or {}
        filename = document.get("source_filename") or job.get("filename")
        decisions = job.get("review_decisions") or {}

        for section in result.get("sections") or []:
            section_name = section.get("section_name")

            for question in section.get("questions") or []:
                if not question.get("review_required", False):
                    continue

                question_id = question.get("question_id")
                if not question_id:
                    continue

                saved_decision = decisions.get(question_id)
                current_decision = (
                    saved_decision.get("decision", "pending")
                    if saved_decision
                    else "pending"
                )

                if current_decision != decision:
                    continue

                question_text = question.get("question") or {}
                searchable_text = " ".join(
                    str(value)
                    for value in (
                        question_text.get("en"),
                        question_text.get("hi"),
                        question.get("question_number"),
                        filename,
                    )
                    if value is not None
                ).casefold()

                if (
                    normalized_search
                    and normalized_search not in searchable_text
                ):
                    continue

                questions.append(
                    {
                        **question,
                        "section_name": section_name,
                        "conversion_id": job.get("conversion_id"),
                        "source_filename": filename,
                        "review_decision": current_decision,
                        "review_note": (
                            saved_decision.get("note")
                            if saved_decision
                            else None
                        ),
                        "reviewed_at": (
                            saved_decision.get("reviewed_at")
                            if saved_decision
                            else None
                        ),
                    }
                )

    total = len(questions)

    return {
        "items": questions[offset:offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
    }

@app.get("/api/answer-keys")
async def get_answer_keys(
    search: str = "",
    status: Literal[
        "all",
        "matched",
        "unmatched",
        "ambiguous",
        "duplicate",
        "conflicting",
        "invalid",
    ] = "all",
    decision: Literal["all", "pending", "approved", "rejected"] = "all",
    limit: int = 25,
    offset: int = 0,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
):
    if len(search) > 200:
        raise HTTPException(status_code=422, detail="Search cannot exceed 200 characters.")

    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 100.")

    if offset < 0:
        raise HTTPException(status_code=422, detail="Offset cannot be negative.")

    normalized_search = search.strip().lower()
    items = []

    jobs, _ = list_jobs(
        limit=10000,
        offset=0,
        organization_id=principal.organization_id,
    )

    for job in jobs:
        if job.get("status") != "completed":
            continue

        answer_key = job.get("answer_key") or {}

        if not answer_key.get("provided"):
            continue

        conversion_id = job.get("conversion_id")
        filename = answer_key.get("filename")
        decisions = job.get("answer_key_decisions") or {}

        for entry in answer_key.get("entries") or []:
            entry_id = entry.get("entry_id")
            saved_decision = decisions.get(entry_id) or {}
            current_decision = saved_decision.get("decision", "pending")

            if status != "all" and entry.get("status") != status:
                continue

            if decision != "all" and current_decision != decision:
                continue

            if normalized_search:
                searchable_text = " ".join(
                    str(value or "")
                    for value in (
                        filename,
                        entry.get("question_number"),
                        entry.get("answer"),
                        entry.get("status"),
                    )
                ).lower()

                if normalized_search not in searchable_text:
                    continue

            items.append({
                **entry,
                "conversion_id": conversion_id,
                "source_filename": filename,
                "review_decision": current_decision,
                "corrected_answer": saved_decision.get("corrected_answer"),
                "review_note": saved_decision.get("note"),
                "reviewed_at": saved_decision.get("reviewed_at"),
            })

    items.sort(
        key=lambda item: (
            item.get("source_filename") or "",
            item.get("question_number") or "",
        )
    )

    total = len(items)

    return {
        "items": items[offset:offset + limit],
        "total": total,
        "limit": limit,
        "offset": offset,
    }

@app.patch("/api/answer-keys/{conversion_id}/entries/{entry_id}")
async def update_answer_key_decision(
    conversion_id: str,
    entry_id: str,
    payload: AnswerKeyDecisionRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    csrf: None = Depends(require_csrf),
):
    reviewed_at = datetime.now(timezone.utc).isoformat()

    try:
        read_job_for_organization(
            conversion_id,
            principal.organization_id,
        )
        saved_decision = save_answer_key_decision(
            conversion_id=conversion_id,
            organization_id=principal.organization_id,
            entry_id=entry_id,
            decision=payload.decision,
            corrected_answer=payload.corrected_answer,
            note=payload.note,
            reviewed_at=reviewed_at,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Conversion not found.")
    except KeyError:
        raise HTTPException(status_code=404, detail="Answer-key entry not found.")
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))

    return {
        "conversion_id": conversion_id,
        "entry_id": entry_id,
        **saved_decision,
    }

@app.post("/api/conversions/{conversion_id}/publish")
async def publish_conversion(
    conversion_id: str,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    csrf: None = Depends(require_csrf),
):
    try:
        read_job_for_organization(
            conversion_id,
            principal.organization_id,
        )
        return create_publication(
            conversion_id,
            principal.organization_id,
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Conversion not found.",
        )

    except ValueError as error:
        raise HTTPException(
            status_code=409,
            detail=str(error),
        )

@app.get("/api/conversions/{conversion_id}/publications")
async def get_publications(
    conversion_id: str,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
):
    try:
        read_job_for_organization(
            conversion_id,
            principal.organization_id,
        )
        publications = list_publications(
            conversion_id,
            principal.organization_id,
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Conversion not found.",
        )

    return {
        "items": publications,
        "total": len(publications),
    }


@app.get("/api/conversions/{conversion_id}/publications/{version}")
async def get_publication(
    conversion_id: str,
    version: int,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
):
    try:
        read_job_for_organization(
            conversion_id,
            principal.organization_id,
        )
        return read_publication(
            conversion_id,
            principal.organization_id,
            version,
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Publication not found.",
        )

@app.patch(
    "/api/review/questions/{conversion_id}/{question_id}"
)
async def update_review_question(
    conversion_id: str,
    question_id: str,
    payload: ReviewDecisionRequest,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    csrf: None = Depends(require_csrf),
):
    reviewed_at = datetime.now(timezone.utc).isoformat()

    try:
        read_job_for_organization(
            conversion_id,
            principal.organization_id,
        )
        saved_decision = save_review_decision(
            conversion_id=conversion_id,
            organization_id=principal.organization_id,
            question_id=question_id,
            decision=payload.decision,
            note=payload.note.strip() if payload.note else None,
            reviewed_at=reviewed_at,
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Conversion not found.",
        )

    except KeyError:
        raise HTTPException(
            status_code=404,
            detail="Question not found.",
        )

    except ValueError:
        raise HTTPException(
            status_code=409,
            detail="Conversion is not completed.",
        )

    return {
        "conversion_id": conversion_id,
        "question_id": question_id,
        **saved_decision,
    }


@app.post("/api/convert")
async def convert(
    background: BackgroundTasks,
    files: list[UploadFile] | None = File(None),
    file: UploadFile | None = File(None),
    roles: str = Form("{}"),
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    csrf: None = Depends(require_csrf),
):
    uploads = files or ([file] if file else [])

    logger.info("Upload request received: files=%d names=%s", len(uploads), [upload.filename for upload in uploads])

    if not uploads:
        raise HTTPException(
            status_code=400,
            detail="No file received. Please select a PDF, DOCX or TXT file.",
        )
    if len(uploads) > 2:
        raise HTTPException(
            status_code=400,
            detail="Upload one question paper and optionally one answer key.",
        )

    try:
        role_data = json.loads(roles)

        if not isinstance(role_data, dict):
            raise ValueError("Roles must be a JSON object.")

    except Exception:
        raise HTTPException(
            status_code=400,
            detail="Invalid roles field.",
        )

    normalized_names = [Path(upload.filename or "").name for upload in uploads]
    if len(set(normalized_names)) != len(normalized_names):
        raise HTTPException(status_code=400, detail="Uploaded filenames must be unique when assigning roles.")

    effective_roles = {
        name: role_data.get(name, "question_paper" if len(uploads) == 1 else ("question_paper" if index == 0 else "answer_key"))
        for index, name in enumerate(normalized_names)
    }
    if set(role_data) - set(normalized_names):
        raise HTTPException(status_code=400, detail="Roles contain filenames that were not uploaded.")
    if any(role not in {"question_paper", "answer_key"} for role in effective_roles.values()):
        raise HTTPException(status_code=400, detail="Invalid file role. Use question_paper or answer_key.")
    question_papers = [name for name, role in effective_roles.items() if role == "question_paper"]
    if len(question_papers) != 1:
        raise HTTPException(
            status_code=400,
            detail="Upload exactly one question paper and optionally one answer key.",
        )

    conversion_id, root = create_job(
        organization_id=principal.organization_id,
        created_by=principal.user_id,
    )

    question_paper_name = question_papers[0]

    update_job(
        conversion_id,
        filename=question_paper_name,
        format=Path(question_paper_name).suffix.lstrip(".").lower(),
    )
    logger.info("Conversion %s accepted; roles=%s", conversion_id, effective_roles)

    saved_files = []
    role_map = {}
    source_name_map = {}

    total_size = 0
    maximum_size = settings.max_upload_mb * 1024 * 1024

    try:
        for index, upload in enumerate(uploads):
            original_name = Path(
                upload.filename or f"upload_{index}"
            ).name

            extension = Path(
                original_name
            ).suffix.lower()

            if extension not in ALLOWED_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"Unsupported file type: {original_name}",
                )

            role = effective_roles[original_name]

            destination = (
                root / f"input_{index}{extension}"
            )

            with destination.open("wb") as output:
                while True:
                    chunk = await upload.read(
                        1024 * 1024
                    )

                    if not chunk:
                        break

                    total_size += len(chunk)

                    if total_size > maximum_size:
                        raise HTTPException(
                            status_code=413,
                            detail=(
                                f"Combined upload exceeds "
                                f"{settings.max_upload_mb} MB."
                            ),
                        )

                    output.write(chunk)

            if destination.stat().st_size == 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"{original_name} is empty.",
                )

            saved_files.append(destination)
            role_map[destination.name] = role
            source_name_map[destination.name] = original_name
            logger.info("Validated upload: conversion=%s filename=%s role=%s size=%d destination=%s", conversion_id, original_name, role, destination.stat().st_size, destination)

            await upload.close()

        background.add_task(
            run_conversion,
            conversion_id,
            saved_files,
            role_map,
            root,
            source_name_map,
        )
        logger.info("Conversion %s queued with %d files", conversion_id, len(saved_files))

        return read_job(conversion_id)

    except Exception:
        logger.exception(
            "Upload validation/save failed for conversion %s",
            conversion_id,
        )

        try:
            delete_job(
                conversion_id,
                principal.organization_id,
            )
        except FileNotFoundError:
            pass

        shutil.rmtree(root, ignore_errors=True)
        raise

    finally:
        for upload in uploads:
            try:
                await upload.close()
            except Exception:
                pass


@app.get("/api/conversions/{conversion_id}")
async def status(
    conversion_id: str,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
):
    try:
        return read_job_for_organization(
            conversion_id,
            principal.organization_id,
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Conversion not found.",
        )

@app.get("/api/conversions/{conversion_id}/json")
async def download_json(
    conversion_id: str,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
):
    try:
        data = read_job_for_organization(
            conversion_id,
            principal.organization_id,
        )
        root = job_dir_for_organization(
            conversion_id,
            principal.organization_id,
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Conversion not found.",
        )

    if data["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail="Conversion is not complete.",
        )

    path = root / "result.json"

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="JSON result is unavailable.",
        )

    source_name = data["result"]["document"]["source_filename"]
    stem = Path(source_name).stem or "docujson"

    return FileResponse(
        path,
        media_type="application/json",
        filename=f"{stem}.json",
    )


@app.get("/api/conversions/{conversion_id}/zip")
async def download_zip(
    conversion_id: str,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
):
    try:
        data = read_job_for_organization(
            conversion_id,
            principal.organization_id,
        )
        root = job_dir_for_organization(
            conversion_id,
            principal.organization_id,
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Conversion not found.",
        )

    if data["status"] != "completed":
        raise HTTPException(
            status_code=409,
            detail="Conversion is not complete.",
        )

    result_path = root / "result.json"

    if not result_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="JSON result is unavailable.",
        )

    archive_path = root / "download.zip"

    with zipfile.ZipFile(
        archive_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:

        archive.write(
            result_path,
            arcname="document.json",
        )

        debug_path = root / "extraction_debug.json"
        if debug_path.is_file():
            archive.write(debug_path, arcname="debug/extraction_debug.json")

        classification_debug_path = root / "classification_debug.json"
        if classification_debug_path.is_file():
            archive.write(classification_debug_path, arcname="debug/classification_debug.json")

        manifest_path = root / "media_manifest.json"
        if manifest_path.is_file():
            archive.write(manifest_path, arcname="media/manifest.json")

        media_dir = root / "media"

        if media_dir.exists():
            for media_file in media_dir.iterdir():
                if media_file.is_file():
                    archive.write(
                        media_file,
                        arcname=f"media/{media_file.name}",
                    )

    source_name = data["result"]["document"]["source_filename"]
    stem = Path(source_name).stem or "docujson"

    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename=f"{stem}_with_media.zip",
    )


@app.get(
    "/api/conversions/{conversion_id}/media/{filename}"
)
async def media(
    conversion_id: str,
    filename: str,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
):
    if (
        Path(filename).name != filename
        or not re.fullmatch(r"[\w.-]+", filename)
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid filename.",
        )

    try:
        root = job_dir_for_organization(
            conversion_id,
            principal.organization_id,
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Conversion not found.",
        )

    path = root / "media" / filename

    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Media not found.",
        )

    return FileResponse(path)


@app.delete("/api/conversions/{conversion_id}")
async def delete_conversion(
    conversion_id: str,
    principal: AuthenticatedPrincipal = Depends(get_current_principal),
    csrf: None = Depends(require_csrf),
):
    try:
        root = job_dir_for_organization(
            conversion_id,
            principal.organization_id,
        )

        delete_job(
            conversion_id,
            principal.organization_id,
        )

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Conversion not found.",
        )

    shutil.rmtree(root, ignore_errors=True)

    return {
        "deleted": True,
        "conversion_id": conversion_id,
    }