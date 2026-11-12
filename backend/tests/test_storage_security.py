from __future__ import annotations

import pytest

from app.config import settings
from app.storage import job_dir, write_job


@pytest.mark.parametrize(
    "conversion_id",
    ["..", "../outside", "00000000000000000000000000000000/..", "not-a-uuid"],
)
def test_storage_rejects_non_generated_conversion_ids(tmp_path, monkeypatch, conversion_id):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "storage"))
    storage_root = settings.storage_path
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("preserve", encoding="utf-8")

    with pytest.raises(FileNotFoundError, match="Conversion not found"):
        job_dir(conversion_id)

    with pytest.raises(FileNotFoundError, match="Conversion not found"):
        write_job(conversion_id, {"status": "completed"})

    assert sentinel.read_text(encoding="utf-8") == "preserve"
    assert list(storage_root.iterdir()) == []


def test_generated_uuid_hex_conversion_id_is_accepted(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "storage"))
    conversion_id = "0123456789abcdef0123456789abcdef"
    expected = settings.storage_path / conversion_id
    expected.mkdir()

    assert job_dir(conversion_id) == expected
