import io
import json
import zipfile

import fitz
import pytest
from docx import Document
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "storage"))
    monkeypatch.setattr(settings, "max_upload_mb", 1)
    with TestClient(app) as test_client:
        yield test_client


def make_docx():
    document = Document()
    document.add_paragraph("Sample question paper")
    document.add_paragraph("1. What is 2 + 2?")
    document.add_paragraph("A. 3")
    document.add_paragraph("B. 4")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def make_pdf():
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Sample question paper\n1. What is 2 + 2?\nA. 3\nB. 4")
    content = document.tobytes()
    document.close()
    return content


def upload(client, filename="questions.txt", content=b"Sample question paper\n1. What is 2 + 2?\nA. 3\nB. 4\n", roles=None):
    data = {"roles": json.dumps(roles or {filename: "question_paper"})}
    response = client.post("/api/convert", files={"files": (filename, content)}, data=data)
    return response


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "ollama": {"enabled": False, "available": False, "model": None}}


@pytest.mark.parametrize(("filename", "content"), [
    ("questions.txt", b"1. TXT question\nA. one\nB. two"),
    ("questions.docx", make_docx()),
    ("questions.pdf", make_pdf()),
])
def test_valid_document_formats_complete_and_download(client, filename, content):
    response = upload(client, filename, content)
    assert response.status_code == 200
    queued = response.json()
    assert queued["status"] == "queued"
    assert queued["progress"] == 0
    conversion_id = queued["conversion_id"]
    status = client.get(f"/api/conversions/{conversion_id}")
    assert status.status_code == 200
    assert status.json()["status"] == "completed"
    saved = list((settings.storage_path / conversion_id).glob("input_*"))
    assert len(saved) == 1 and saved[0].read_bytes() == content
    json_response = client.get(f"/api/conversions/{conversion_id}/json")
    assert json_response.status_code == 200
    assert json.loads(json_response.content)["document"]["source_format"] == filename.rsplit(".", 1)[1]
    zip_response = client.get(f"/api/conversions/{conversion_id}/zip")
    assert zip_response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(zip_response.content)) as archive:
        assert "document.json" in archive.namelist()


def test_legacy_single_file_field(client):
    response = client.post("/api/convert", files={"file": ("legacy.txt", b"legacy body")})
    assert response.status_code == 200
    assert response.json()["status"] == "queued"


@pytest.mark.parametrize(("filename", "content", "status"), [
    ("payload.exe", b"no", 400),
    ("empty.txt", b"", 400),
    ("large.txt", b"x" * (1024 * 1024 + 1), 413),
])
def test_rejects_invalid_upload(client, filename, content, status):
    response = upload(client, filename, content)
    assert response.status_code == status
    assert response.json()["detail"]


def test_multiple_files_with_explicit_roles_and_saved(client):
    files = [
        ("files", ("paper.txt", b"1. question")),
        ("files", ("key.txt", b"1. B")),
    ]
    response = client.post("/api/convert", files=files, data={"roles": json.dumps({"paper.txt": "question_paper", "key.txt": "answer_key"})})
    assert response.status_code == 200
    conversion_id = response.json()["conversion_id"]
    root = settings.storage_path / conversion_id
    assert (root / "input_0.txt").read_bytes() == b"1. question"
    assert (root / "input_1.txt").read_bytes() == b"1. B"
    assert client.get(f"/api/conversions/{conversion_id}").json()["status"] == "completed"


def test_reject_multiple_or_missing_question_papers(client):
    pair = [("files", ("one.txt", b"one")), ("files", ("two.txt", b"two"))]
    both_papers = client.post("/api/convert", files=pair, data={"roles": json.dumps({"one.txt": "question_paper", "two.txt": "question_paper"})})
    assert both_papers.status_code == 400
    missing = client.post("/api/convert", files={"files": ("key.txt", b"key")}, data={"roles": json.dumps({"key.txt": "answer_key"})})
    assert missing.status_code == 400


def test_media_endpoint_and_unknown_conversion(client):
    response = upload(client)
    conversion_id = response.json()["conversion_id"]
    media_dir = settings.storage_path / conversion_id / "media"
    media_dir.mkdir(exist_ok=True)
    (media_dir / "sample.png").write_bytes(b"image data")
    media_response = client.get(f"/api/conversions/{conversion_id}/media/sample.png")
    assert media_response.status_code == 200
    assert media_response.content == b"image data"
    assert client.get("/api/conversions/missing").status_code == 404
    assert client.get("/api/conversions/missing/json").status_code == 404
    assert client.get("/api/conversions/missing/zip").status_code == 404
    assert client.get("/api/conversions/missing/media/no.png").status_code == 404
