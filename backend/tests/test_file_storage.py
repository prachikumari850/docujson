import asyncio
from io import BytesIO
from pathlib import Path

import pytest

from app.config import settings
from app.services.file_storage import (
    create_conversion_directory,
    delete_conversion_directory,
    get_conversion_directory,
    get_publications_directory,
    read_json_file,
    save_upload,
    validate_conversion_id,
    write_job_status,
    write_publication_file,
    get_publication_file,
    list_publication_files,
)

class MockUpload:
    def __init__(self, content: bytes):
        self.content = content
        self.position = 0

    async def read(self, size: int = -1):
        if size < 0:
            size = len(self.content) - self.position

        chunk = self.content[self.position:self.position + size]
        self.position += len(chunk)
        return chunk


@pytest.fixture
def storage_root(tmp_path, monkeypatch):
    monkeypatch.setattr(
        settings,
        "storage_dir",
        str(tmp_path / "storage"),
    )
    return settings.storage_path


def test_create_conversion_directory_creates_media_folder(storage_root):
    conversion_id = "a" * 32

    directory = create_conversion_directory(conversion_id)

    assert directory == storage_root / conversion_id
    assert directory.is_dir()
    assert (directory / "media").is_dir()


@pytest.mark.parametrize(
    "conversion_id",
    [
        "..",
        "../outside",
        "not-a-valid-id",
        "a" * 31,
        "a" * 33,
    ],
)
def test_validate_conversion_id_rejects_invalid_values(conversion_id):
    with pytest.raises(FileNotFoundError):
        validate_conversion_id(conversion_id)


def test_get_conversion_directory_rejects_missing_directory(storage_root):
    with pytest.raises(FileNotFoundError):
        get_conversion_directory("a" * 32)


def test_save_upload_streams_file(storage_root):
    conversion_id = "a" * 32
    create_conversion_directory(conversion_id)

    destination, total = asyncio.run(
        save_upload(
            conversion_id=conversion_id,
            filename="input_0.pdf",
            upload=MockUpload(b"document-content"),
            max_bytes=1024,
            chunk_size=4,
        )
    )

    assert destination.read_bytes() == b"document-content"
    assert total == len(b"document-content")


def test_save_upload_rejects_size_limit(storage_root):
    conversion_id = "a" * 32
    create_conversion_directory(conversion_id)

    with pytest.raises(ValueError, match="Upload size limit exceeded"):
        asyncio.run(
            save_upload(
                conversion_id=conversion_id,
                filename="input_0.pdf",
                upload=MockUpload(b"document-content"),
                max_bytes=5,
                chunk_size=4,
            )
        )

    assert not (storage_root / conversion_id / "input_0.pdf").exists()


def test_save_upload_rejects_empty_file(storage_root):
    conversion_id = "a" * 32
    create_conversion_directory(conversion_id)

    with pytest.raises(ValueError, match="Uploaded file is empty"):
        asyncio.run(
            save_upload(
                conversion_id=conversion_id,
                filename="input_0.txt",
                upload=MockUpload(b""),
                max_bytes=1024,
            )
        )

    assert not (storage_root / conversion_id / "input_0.txt").exists()


def test_save_upload_rejects_existing_destination(storage_root):
    conversion_id = "a" * 32
    directory = create_conversion_directory(conversion_id)

    existing = directory / "input_0.pdf"
    existing.write_bytes(b"original")

    with pytest.raises(FileExistsError):
        asyncio.run(
            save_upload(
                conversion_id=conversion_id,
                filename="input_0.pdf",
                upload=MockUpload(b"replacement"),
                max_bytes=1024,
            )
        )

    assert existing.read_bytes() == b"original"


def test_delete_conversion_directory_removes_only_target(storage_root):
    conversion_id = "a" * 32
    directory = create_conversion_directory(conversion_id)

    (directory / "source.txt").write_text(
        "test content",
        encoding="utf-8",
    )

    assert delete_conversion_directory(conversion_id) is True
    assert not directory.exists()
    assert storage_root.is_dir()


def test_delete_conversion_directory_returns_false_if_missing(storage_root):
    assert delete_conversion_directory("a" * 32) is False


def test_delete_conversion_directory_rejects_invalid_id(storage_root):
    with pytest.raises(FileNotFoundError):
        delete_conversion_directory("../outside")

def test_get_conversion_directory_rejects_symlink(storage_root):
    target_id = "b" * 32
    symlink_id = "a" * 32

    target = create_conversion_directory(target_id)
    symlink = storage_root / symlink_id

    try:
        symlink.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Directory symlinks are not supported.")

    with pytest.raises(FileNotFoundError):
        get_conversion_directory(symlink_id)

def test_publication_directory_creation(storage_root):
    conversion_id = "a" * 32
    create_conversion_directory(conversion_id)

    directory = get_publications_directory(
        conversion_id,
        create=True,
    )

    assert directory.is_dir()
    assert directory == storage_root / conversion_id / "publications"


def test_write_and_read_publication_file(storage_root):
    conversion_id = "a" * 32
    create_conversion_directory(conversion_id)

    publication = {
        "publication_id": f"{conversion_id}-v1",
        "version": 1,
        "total_questions": 2,
    }

    path = write_publication_file(
        conversion_id,
        1,
        publication,
    )

    assert path.is_file()
    assert read_json_file(path) == publication
    assert not path.with_suffix(".tmp").exists()


def test_write_job_status(storage_root):
    conversion_id = "a" * 32
    create_conversion_directory(conversion_id)

    status = {
        "status": "completed",
        "progress": 100,
    }

    write_job_status(conversion_id, status)

    status_path = storage_root / conversion_id / "status.json"

    assert read_json_file(status_path) == status
    assert not (storage_root / conversion_id / "status.tmp").exists()

def test_list_publication_files(storage_root):
    conversion_id = "a" * 32
    create_conversion_directory(conversion_id)

    write_publication_file(
        conversion_id,
        1,
        {"version": 1},
    )
    write_publication_file(
        conversion_id,
        2,
        {"version": 2},
    )

    files = list_publication_files(conversion_id)

    assert len(files) == 2
    assert all(path.is_file() for path in files)


def test_list_publication_files_returns_empty(storage_root):
    conversion_id = "a" * 32
    create_conversion_directory(conversion_id)

    assert list_publication_files(conversion_id) == []


def test_get_publication_file_returns_existing_version(storage_root):
    conversion_id = "a" * 32
    create_conversion_directory(conversion_id)

    write_publication_file(
        conversion_id,
        1,
        {"version": 1},
    )

    path = get_publication_file(conversion_id, 1)

    assert path.is_file()
    assert path.name == "version-0001.json"


@pytest.mark.parametrize("version", [0, -1, 999])
def test_get_publication_file_rejects_invalid_or_missing_version(
    storage_root,
    version,
):
    conversion_id = "a" * 32
    create_conversion_directory(conversion_id)

    with pytest.raises(FileNotFoundError):
        get_publication_file(conversion_id, version)