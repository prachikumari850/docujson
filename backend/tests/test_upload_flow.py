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


def make_vector_diagram_pdf():
    document = fitz.open()
    page = document.new_page(width=360, height=440)
    page.insert_text((45, 55), "1. Select the graph with an increasing curve.")
    page.draw_line((105, 250), (245, 250), color=(0, 0, 0), width=1.2)
    page.draw_line((115, 265), (115, 125), color=(0, 0, 0), width=1.2)
    page.draw_line((115, 250), (150, 220), color=(0.1, 0.2, 0.8), width=1.5)
    page.draw_bezier((150, 220), (175, 190), (205, 160), (235, 135), color=(0.1, 0.2, 0.8), width=1.5)
    page.draw_line((238, 135), (230, 138), color=(0.1, 0.2, 0.8), width=1.5)
    page.insert_text((248, 253), "x")
    page.insert_text((108, 120), "y")
    page.insert_text((45, 325), "(1) graph A    (2) graph B    (3) graph C")
    data = document.tobytes()
    document.close()
    return data


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
    exported = json.loads(json_response.content)
    assert exported["document"]["document_id"]
    assert exported["document"]["source_sha256"]
    assert exported["document"]["extraction_date"]
    assert exported["document"]["schema_version"] == "2.1"
    zip_response = client.get(f"/api/conversions/{conversion_id}/zip")
    assert zip_response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(zip_response.content)) as archive:
        assert "document.json" in archive.namelist()
        zipped = json.loads(archive.read("document.json"))
        assert zipped == exported


def test_vector_graph_export_and_zip_paths_are_genuine_and_portable(client):
    response = upload(client, "graph.pdf", make_vector_diagram_pdf())
    assert response.status_code == 200
    conversion_id = response.json()["conversion_id"]
    status = client.get(f"/api/conversions/{conversion_id}").json()
    assert status["status"] == "completed", status.get("error")
    questions = [question for section in status["result"]["sections"] for question in section["questions"]]
    assert len(questions) == 1
    json_result = client.get(f"/api/conversions/{conversion_id}/json").json()
    assert json_result["sections"] == status["result"]["sections"]
    assert json_result["document"]["document_id"] == json_result["document"]["source_sha256"][:16]
    question = questions[0]
    assert question["stable_id"].startswith(json_result["document"]["document_id"][:12])
    assert question["section"]
    assert all(option["stable_id"].startswith(question["stable_id"]) for option in question["options"])
    assert question["ordered_segments"]

    media_items = [asset for question in questions for asset in question.get("media", [])]
    media_items.extend(asset for question in questions for option in question["options"] for asset in option.get("media", []))
    vector_items = [asset for asset in media_items if asset.get("media_format") == "svg_vector"]
    assert vector_items, "The synthetic PDF's source drawing geometry should yield genuine SVG."
    zip_response = client.get(f"/api/conversions/{conversion_id}/zip")
    assert zip_response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(zip_response.content)) as archive:
        names = set(archive.namelist())
        assert "media/manifest.json" in names
        for asset in media_items:
            assert asset["relative_path"] in names
            if asset.get("svg_relative_path"):
                assert asset["svg_relative_path"] in names
        import xml.etree.ElementTree as ET
        for asset in vector_items:
            root = ET.fromstring(archive.read(asset["svg_relative_path"]))
            assert root.tag == "{http://www.w3.org/2000/svg}svg"
            assert root.find(".//{http://www.w3.org/2000/svg}path") is not None
            assert root.find(".//{http://www.w3.org/2000/svg}image") is None
    svg_response = client.get(f"/api/conversions/{conversion_id}/media/{vector_items[0]['svg_filename']}")
    assert svg_response.status_code == 200
    assert svg_response.headers["content-type"].startswith("image/svg+xml")


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


def test_conversion_matches_table_answer_key_by_question_number(client):
    paper = b"SECTION A\n1. First question\n(1) one\n(2) two\n(3) three\n(4) four\n2. Second question\n(1) one\n(2) two\n(3) three\n(4) four\n3. Third question\n(1) one\n(2) two\n(3) three\n(4) four"
    key = b"Q. 1 2 3\nA. 3 4 1"
    files = [("files", ("paper.txt", paper)), ("files", ("key.txt", key))]
    roles = {"paper.txt": "question_paper", "key.txt": "answer_key"}
    response = client.post("/api/convert", files=files, data={"roles": json.dumps(roles)})
    assert response.status_code == 200
    result = client.get(f"/api/conversions/{response.json()['conversion_id']}").json()["result"]
    questions = [question for section in result["sections"] for question in section["questions"]]
    assert [question["correct_answer"] for question in questions] == ["3", "4", "1"]
    assert result["document"]["answer_key_provided"] is True
    assert result["document"]["answer_key_extracted"] == 3
    assert result["document"]["answer_key_matched"] == 3


def test_official_50_entry_key_maps_to_numbered_question_paper(client):
    expected = [3, 4, 1, 2, 1, 1, 4, 1, 1, 2, 2, 2, 1, 2, 3, 1, 2, 4, 1, 1, 1, 1, 1, 1, 3, 4, 2, 1, 3, 3, 4, 3, 3, 2, 1, 4, 3, 3, 3, 3, 2, 3, 2, 2, 3, 3, 1, 4, 2, 1]
    questions = ["SECTION A"]
    for number in range(1, 36):
        questions.extend([f"{number}. Question {number} text", "(1) option one", "(2) option two", "(3) option three", "(4) option four"])
    questions.append("SECTION B")
    for number in range(36, 51):
        questions.extend([f"{number}. Question {number} text", "(1) option one", "(2) option two", "(3) option three", "(4) option four"])
    key_parts = []
    for start, end in ((1, 30), (31, 50)):
        key_parts.append("Q. " + " ".join(map(str, range(start, end + 1))))
        key_parts.append("A. " + " ".join(map(str, expected[start - 1:end])))
    files = [("files", ("srg.txt", "\n".join(questions).encode())), ("files", ("key.txt", "\n".join(key_parts).encode()))]
    roles = {"srg.txt": "question_paper", "key.txt": "answer_key"}
    response = client.post("/api/convert", files=files, data={"roles": json.dumps(roles)})
    assert response.status_code == 200
    result = client.get(f"/api/conversions/{response.json()['conversion_id']}").json()["result"]
    extracted = [question for section in result["sections"] for question in section["questions"]]
    assert len(extracted) == 50
    assert [question["question_number"] for question in extracted] == list(range(1, 51))
    assert [int(question["correct_answer"]) for question in extracted] == expected
    assert [len(section["questions"]) for section in result["sections"]] == [35, 15]
    assert result["document"]["answer_key_extracted"] == 50
    assert result["document"]["answer_key_matched"] == 50


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
