import json
from pathlib import Path
from threading import RLock
from uuid import uuid4

from app.config import settings


LOCK = RLock()


def create_job():
    conversion_id = uuid4().hex
    root = settings.storage_path / conversion_id

    (root / "media").mkdir(parents=True, exist_ok=True)

    write_job(
        conversion_id,
        {
            "conversion_id": conversion_id,
            "status": "queued",
            "progress": 0,
            "stage": "Waiting to start",
            "error": None,
            "result": None,
        },
    )

    return conversion_id, root


def job_dir(conversion_id: str) -> Path:
    path = settings.storage_path / conversion_id

    if not path.is_dir():
        raise FileNotFoundError("Conversion not found.")

    return path


def write_job(conversion_id: str, data: dict):
    root = settings.storage_path / conversion_id
    root.mkdir(parents=True, exist_ok=True)

    temporary = root / "status.tmp"
    destination = root / "status.json"

    with LOCK:
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(destination)


def read_job(conversion_id: str) -> dict:
    with LOCK:
        path = job_dir(conversion_id) / "status.json"

        if not path.is_file():
            raise FileNotFoundError("Conversion not found.")

        return json.loads(
            path.read_text(encoding="utf-8")
        )


def update_job(conversion_id: str, **values):
    with LOCK:
        data = read_job(conversion_id)
        data.update(values)
        write_job(conversion_id, data)
        return data