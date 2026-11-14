import json
from pathlib import Path
import re
import shutil

from app.config import settings


CONVERSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
CHUNK_SIZE = 1024 * 1024


def validate_conversion_id(conversion_id: str) -> str:
    if (
        not isinstance(conversion_id, str)
        or not CONVERSION_ID_RE.fullmatch(conversion_id)
    ):
        raise FileNotFoundError("Conversion not found.")

    return conversion_id


def get_storage_root() -> Path:
    return settings.storage_path.resolve()


def get_conversion_directory(
    conversion_id: str,
    *,
    must_exist: bool = True,
) -> Path:
    conversion_id = validate_conversion_id(conversion_id)

    root = get_storage_root()
    candidate = root / conversion_id

    if candidate.is_symlink():
        raise FileNotFoundError("Conversion not found.")

    directory = candidate.resolve()

    if directory.parent != root:
        raise FileNotFoundError("Conversion not found.")

    if must_exist and not directory.is_dir():
        raise FileNotFoundError("Conversion not found.")

    return directory


def create_conversion_directory(conversion_id: str) -> Path:
    directory = get_conversion_directory(
        conversion_id,
        must_exist=False,
    )

    directory.mkdir(parents=True, exist_ok=False)
    (directory / "media").mkdir()

    return directory


async def save_upload(
    conversion_id: str,
    filename: str,
    upload,
    *,
    max_bytes: int,
    current_total: int = 0,
    chunk_size: int = CHUNK_SIZE,
) -> tuple[Path, int]:
    directory = get_conversion_directory(conversion_id)

    safe_filename = Path(filename).name

    if not safe_filename or safe_filename in {".", ".."}:
        raise ValueError("Invalid upload filename.")

    destination = (directory / safe_filename).resolve()

    if destination.parent != directory:
        raise ValueError("Invalid upload destination.")

    total = current_total
    file_created = False

    try:
        with destination.open("xb") as output:
            file_created = True

            while True:
                chunk = await upload.read(chunk_size)

                if not chunk:
                    break

                total += len(chunk)

                if total > max_bytes:
                    raise ValueError("Upload size limit exceeded.")

                output.write(chunk)

        if destination.stat().st_size == 0:
            raise ValueError("Uploaded file is empty.")

        return destination, total

    except Exception:
        if file_created:
            destination.unlink(missing_ok=True)
        raise


def delete_conversion_directory(conversion_id: str) -> bool:
    directory = get_conversion_directory(
        conversion_id,
        must_exist=False,
    )

    if not directory.exists():
        return False

    shutil.rmtree(directory)
    return True

def get_publications_directory(
    conversion_id: str,
    *,
    create: bool = False,
) -> Path:
    conversion_directory = get_conversion_directory(conversion_id)
    publications_directory = conversion_directory / "publications"

    if create:
        publications_directory.mkdir(exist_ok=True)

    if publications_directory.exists() and not publications_directory.is_dir():
        raise FileNotFoundError("Publications directory not found.")

    return publications_directory

def list_publication_files(conversion_id: str) -> list[Path]:
    directory = get_publications_directory(conversion_id)

    if not directory.is_dir():
        return []

    return list(directory.glob("version-*.json"))


def get_publication_file(
    conversion_id: str,
    version: int,
) -> Path:
    if version < 1:
        raise FileNotFoundError("Publication not found.")

    directory = get_publications_directory(conversion_id)
    path = directory / f"version-{version:04d}.json"

    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError("Publication not found.")

    return path

def write_publication_file(
    conversion_id: str,
    version: int,
    publication: dict,
) -> Path:
    if version < 1:
        raise ValueError("Publication version must be positive.")

    directory = get_publications_directory(
        conversion_id,
        create=True,
    )

    destination = directory / f"version-{version:04d}.json"
    temporary = directory / f"version-{version:04d}.tmp"

    try:
        temporary.write_text(
            json.dumps(publication, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise

    return destination


def read_json_file(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def write_job_status(conversion_id: str, data: dict) -> None:
    root = get_conversion_directory(conversion_id)

    temporary = root / "status.tmp"
    destination = root / "status.json"

    try:
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise