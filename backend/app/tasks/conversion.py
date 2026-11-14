
from pathlib import Path

from app import database
from app.celery_app import celery_app
from app.services.file_storage import get_conversion_directory
from app.services.engine import run_conversion
from app.storage import read_job


@celery_app.task(
    bind=True,
    name="app.tasks.conversion.process_conversion",
    acks_late=True,
)
def process_conversion(
    self,
    conversion_id: str,
    source_filenames: list[str],
    role_map: dict,
    source_name_map: dict,
):
    # Reuse an existing connection (including the test fixture's mock).
    connection_already_open = database.mongo_client is not None

    database.connect_to_mongo()

    try:
        root = get_conversion_directory(conversion_id)

        source_files = []

        for filename in source_filenames:
            if (
                not filename
                or Path(filename).name != filename
                or filename in {".", ".."}
            ):
                raise ValueError("Invalid source filename.")

            path = root / filename

            if path.is_symlink() or not path.is_file():
                raise FileNotFoundError(
                    f"Source file not found: {filename}"
                )

            source_files.append(path)

        run_conversion(
            conversion_id=conversion_id,
            source_files=source_files,
            role_map=role_map,
            root=root,
            source_name_map=source_name_map,
        )

        job = read_job(conversion_id)

        if job.get("status") == "failed":
            raise RuntimeError(
                job.get("error") or "Document conversion failed."
            )

        return {
            "conversion_id": conversion_id,
            "status": job.get("status"),
        }

    finally:
        # Only close connections opened by this task.
        if not connection_already_open:
            database.close_mongo_connection()
