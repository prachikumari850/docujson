import json
import logging
import re
import shutil
import zipfile
from pathlib import Path

import httpx
from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import settings
from app.storage import (
    create_job,
    job_dir,
    read_job,
    update_job,
)
from app.services.engine import run_conversion


logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("docujson")

app = FastAPI(
    title="DocuJSON API",
    version="2.0.0",
)

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

                available = any(
                    model.get("name", "").split(":")[0]
                    == settings.ollama_model.split(":")[0]
                    for model in models
                )

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


@app.post("/api/convert")
async def convert(
    background: BackgroundTasks,
    files: list[UploadFile] | None = File(None),
    file: UploadFile | None = File(None),
    roles: str = Form("{}"),
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

    conversion_id, root = create_job()
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
        logger.exception("Upload validation/save failed for conversion %s", conversion_id)
        shutil.rmtree(root, ignore_errors=True)
        raise

    finally:
        for upload in uploads:
            try:
                await upload.close()
            except Exception:
                pass


@app.get("/api/conversions/{conversion_id}")
async def status(conversion_id: str):
    try:
        return read_job(conversion_id)

    except FileNotFoundError:
        raise HTTPException(
            status_code=404,
            detail="Conversion not found.",
        )


@app.get("/api/conversions/{conversion_id}/json")
async def download_json(conversion_id: str):
    try:
        data = read_job(conversion_id)
        root = job_dir(conversion_id)

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
async def download_zip(conversion_id: str):
    try:
        data = read_job(conversion_id)
        root = job_dir(conversion_id)

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
        root = job_dir(conversion_id)

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
async def delete_conversion(conversion_id: str):
    try:
        root = job_dir(conversion_id)

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
