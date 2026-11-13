import io
import json
import zipfile

import fitz
import pytest
from docx import Document
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.storage import create_job, read_job, update_job

from app.dependencies.auth import (
    AuthenticatedPrincipal,
    get_current_principal,
)

from app.dependencies.security import require_csrf

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "storage"))
    monkeypatch.setattr(settings, "max_upload_mb", 1)

    app.dependency_overrides[get_current_principal] = lambda: (
        AuthenticatedPrincipal(
            user_id="test-user-123",
            organization_id="test-org-123",
            role="owner",
        )
    )
    app.dependency_overrides[require_csrf] = lambda: None

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_current_principal, None)
        app.dependency_overrides.pop(require_csrf, None)


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

def upload_with_answer_key(
    client,
    paper_filename="paper.txt",
    key_filename="official_key.txt",
):
    paper = (
        b"SECTION A\n"
        b"1. First question\n"
        b"(1) one\n"
        b"(2) two\n"
        b"(3) three\n"
        b"(4) four\n"
        b"2. Second question\n"
        b"(1) alpha\n"
        b"(2) beta\n"
        b"(3) gamma\n"
        b"(4) delta"
    )

    key = b"Q. 1\nA. 3\nQ. 2\nA. 2"

    roles = {
        paper_filename: "question_paper",
        key_filename: "answer_key",
    }

    response = client.post(
        "/api/convert",
        files=[
            ("files", (paper_filename, paper)),
            ("files", (key_filename, key)),
        ],
        data={"roles": json.dumps(roles)},
    )

    assert response.status_code == 200

    return response.json()["conversion_id"]


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



def test_documents_list_returns_completed_conversion_summary(client):
    response = upload(client, "biology.txt")

    assert response.status_code == 200

    conversion_id = response.json()["conversion_id"]

    listing = client.get("/api/documents")

    assert listing.status_code == 200

    data = listing.json()

    assert data["total"] == 1
    assert len(data["items"]) == 1

    document = data["items"][0]

    assert document["conversion_id"] == conversion_id
    assert document["status"] == "completed"
    assert document["filename"] == "biology.txt"
    assert document["format"] == "txt"
    assert document["total_questions"] >= 0

    assert "result" not in document
    assert "storage_path" not in document


def test_documents_list_supports_pagination(client):
    first = upload(client, "first.txt")
    second = upload(client, "second.txt")

    assert first.status_code == 200
    assert second.status_code == 200

    first_page = client.get("/api/documents?limit=1&offset=0")
    second_page = client.get("/api/documents?limit=1&offset=1")

    assert first_page.status_code == 200
    assert second_page.status_code == 200

    first_data = first_page.json()
    second_data = second_page.json()

    assert first_data["total"] == 2
    assert second_data["total"] == 2
    assert len(first_data["items"]) == 1
    assert len(second_data["items"]) == 1

    assert (
        first_data["items"][0]["conversion_id"]
        != second_data["items"][0]["conversion_id"]
    )


@pytest.mark.parametrize(
    "query",
    [
        "?limit=0",
        "?limit=101",
        "?offset=-1",
    ],
)
def test_documents_list_rejects_invalid_pagination(client, query):
    response = client.get(f"/api/documents{query}")

    assert response.status_code == 422



def test_questions_list_returns_extracted_questions(client):
    response = upload(
        client,
        "biology.txt",
        b"1. What is photosynthesis?\nA. Respiration\nB. Food production in plants\nC. Digestion\nD. Transpiration",
    )

    assert response.status_code == 200

    listing = client.get("/api/questions")

    assert listing.status_code == 200

    data = listing.json()

    assert data["total"] >= 1
    assert len(data["items"]) >= 1

    question = data["items"][0]

    assert question["conversion_id"] == response.json()["conversion_id"]
    assert question["source_filename"] == "biology.txt"
    assert "question" in question
    assert "options" in question


def test_questions_list_supports_search(client):
    response = upload(
        client,
        "biology.txt",
        b"1. What is photosynthesis?\nA. Respiration\nB. Food production in plants\nC. Digestion\nD. Transpiration",
    )

    assert response.status_code == 200

    listing = client.get("/api/questions", params={"search": "photosynthesis"})

    assert listing.status_code == 200
    assert listing.json()["total"] >= 1


def test_questions_list_supports_pagination(client):
    first = upload(client, "first.txt")
    second = upload(client, "second.txt")

    assert first.status_code == 200
    assert second.status_code == 200

    listing = client.get("/api/questions", params={"limit": 1, "offset": 0})

    assert listing.status_code == 200
    assert listing.json()["limit"] == 1
    assert len(listing.json()["items"]) == 1
    assert listing.json()["total"] >= 1


def test_questions_list_rejects_invalid_pagination(client):
    response = client.get("/api/questions", params={"limit": 101})

    assert response.status_code == 422


def test_review_queue_returns_flagged_questions(client):
    response = upload(
        client,
        "review.txt",
        b"1. What is photosynthesis?\n"
        b"A. Respiration\n"
        b"B. Food production in plants\n"
        b"C. Digestion\n"
        b"D. Transpiration",
    )

    assert response.status_code == 200

    conversion_id = response.json()["conversion_id"]
    job = read_job(conversion_id)

    question = next(
        question
        for section in job["result"]["sections"]
        for question in section["questions"]
    )

    question["review_required"] = True
    update_job(conversion_id, result=job["result"])

    listing = client.get("/api/review/questions")

    assert listing.status_code == 200

    data = listing.json()

    assert data["total"] == 1
    assert data["items"][0]["question_id"] == question["question_id"]
    assert data["items"][0]["review_decision"] == "pending"


def test_review_question_can_be_approved(client):
    response = upload(
        client,
        "review.txt",
        b"1. What is photosynthesis?\n"
        b"A. Respiration\n"
        b"B. Food production in plants\n"
        b"C. Digestion\n"
        b"D. Transpiration",
    )

    conversion_id = response.json()["conversion_id"]
    job = read_job(conversion_id)

    question = next(
        question
        for section in job["result"]["sections"]
        for question in section["questions"]
    )

    question["review_required"] = True
    update_job(conversion_id, result=job["result"])

    decision = client.patch(
        f"/api/review/questions/{conversion_id}/{question['question_id']}",
        json={
            "decision": "approved",
            "note": "Verified against the source.",
        },
    )

    assert decision.status_code == 200
    assert decision.json()["decision"] == "approved"
    assert decision.json()["note"] == "Verified against the source."
    assert decision.json()["reviewed_at"]

    listing = client.get(
        "/api/review/questions",
        params={"decision": "approved"},
    )

    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    pending = client.get("/api/review/questions")

    assert pending.json()["total"] == 0

    stored_job = read_job(conversion_id)

    assert stored_job["review_decisions"][question["question_id"]]["decision"] == "approved"
    assert stored_job["result"] == job["result"]


def test_review_question_can_be_rejected(client):
    response = upload(
        client,
        "review.txt",
        b"1. What is photosynthesis?\n"
        b"A. Respiration\n"
        b"B. Food production in plants\n"
        b"C. Digestion\n"
        b"D. Transpiration",
    )

    conversion_id = response.json()["conversion_id"]
    job = read_job(conversion_id)

    question = next(
        question
        for section in job["result"]["sections"]
        for question in section["questions"]
    )

    question["review_required"] = True
    update_job(conversion_id, result=job["result"])

    decision = client.patch(
        f"/api/review/questions/{conversion_id}/{question['question_id']}",
        json={"decision": "rejected"},
    )

    assert decision.status_code == 200
    assert decision.json()["decision"] == "rejected"

    listing = client.get(
        "/api/review/questions",
        params={"decision": "rejected"},
    )

    assert listing.json()["total"] == 1


def test_review_question_rejects_missing_conversion(client):
    response = client.patch(
        "/api/review/questions/missing/question-1",
        json={"decision": "approved"},
    )

    assert response.status_code == 404


def test_review_question_rejects_missing_question(client):
    response = upload(client, "review.txt")

    conversion_id = response.json()["conversion_id"]

    decision = client.patch(
        f"/api/review/questions/{conversion_id}/missing-question",
        json={"decision": "approved"},
    )

    assert decision.status_code == 404


def test_review_question_rejects_invalid_decision(client):
    response = upload(client, "review.txt")

    conversion_id = response.json()["conversion_id"]

    decision = client.patch(
        f"/api/review/questions/{conversion_id}/question-1",
        json={"decision": "pending"},
    )

    assert decision.status_code == 422


def test_review_queue_supports_search(client):
    response = upload(
        client,
        "review.txt",
        b"1. What is photosynthesis?\n"
        b"A. Respiration\n"
        b"B. Food production in plants\n"
        b"C. Digestion\n"
        b"D. Transpiration",
    )

    conversion_id = response.json()["conversion_id"]
    job = read_job(conversion_id)

    question = next(
        question
        for section in job["result"]["sections"]
        for question in section["questions"]
    )

    question["review_required"] = True
    update_job(conversion_id, result=job["result"])

    listing = client.get(
        "/api/review/questions",
        params={"search": "photosynthesis"},
    )

    assert listing.status_code == 200
    assert listing.json()["total"] == 1


def test_review_queue_rejects_invalid_pagination(client):
    response = client.get(
        "/api/review/questions",
        params={"limit": 101},
    )

    assert response.status_code == 422


def test_answer_key_metadata_is_persisted_separately_from_result(client):
    paper = (
        b"SECTION A\n"
        b"1. First question\n"
        b"(1) one\n"
        b"(2) two\n"
        b"(3) three\n"
        b"(4) four"
    )
    key = b"Q. 1\nA. 3"

    files = [
        ("files", ("paper.txt", paper)),
        ("files", ("official_key.txt", key)),
    ]
    roles = {
        "paper.txt": "question_paper",
        "official_key.txt": "answer_key",
    }

    response = client.post(
        "/api/convert",
        files=files,
        data={"roles": json.dumps(roles)},
    )

    assert response.status_code == 200

    conversion_id = response.json()["conversion_id"]

    job = client.get(
        f"/api/conversions/{conversion_id}"
    ).json()

    answer_key = job["answer_key"]

    assert answer_key["provided"] is True
    assert answer_key["filename"] == "official_key.txt"
    assert answer_key["total_entries"] == 1
    assert answer_key["matched"] == 1
    assert answer_key["entries"][0]["question_number"] == 1
    assert answer_key["entries"][0]["answer"] == "3"
    assert answer_key["entries"][0]["status"] == "matched"
    assert answer_key["entries"][0]["matched_question_id"]

    assert job["answer_key_decisions"] == {}

    result_file = (
        settings.storage_path
        / conversion_id
        / "result.json"
    )

    result = json.loads(result_file.read_text(encoding="utf-8"))

    assert "answer_key" not in result
    assert result["document"]["answer_key_matched"] == 1


def test_answer_keys_list_entries(client):
    conversion_id = upload_with_answer_key(client)

    response = client.get("/api/answer-keys")

    assert response.status_code == 200

    data = response.json()

    assert data["total"] == 2
    assert len(data["items"]) == 2

    entry = data["items"][0]

    assert entry["conversion_id"] == conversion_id
    assert entry["source_filename"] == "official_key.txt"
    assert entry["review_decision"] == "pending"


def test_answer_keys_support_search(client):
    upload_with_answer_key(client)

    response = client.get(
        "/api/answer-keys",
        params={"search": "official_key.txt"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 2

    response = client.get(
        "/api/answer-keys",
        params={"search": "999"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_answer_keys_support_status_filter(client):
    upload_with_answer_key(client)

    response = client.get(
        "/api/answer-keys",
        params={"status": "matched"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 2

    response = client.get(
        "/api/answer-keys",
        params={"status": "unmatched"},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0


def test_answer_keys_support_pagination(client):
    upload_with_answer_key(client)

    response = client.get(
        "/api/answer-keys",
        params={"limit": 1, "offset": 0},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert len(response.json()["items"]) == 1

    second_page = client.get(
        "/api/answer-keys",
        params={"limit": 1, "offset": 1},
    )

    assert second_page.status_code == 200
    assert len(second_page.json()["items"]) == 1

    assert (
        response.json()["items"][0]["entry_id"]
        != second_page.json()["items"][0]["entry_id"]
    )


def test_answer_key_entry_can_be_approved_with_correction(client):
    conversion_id = upload_with_answer_key(client)

    listing = client.get("/api/answer-keys").json()
    entry = listing["items"][0]

    response = client.patch(
        f"/api/answer-keys/{conversion_id}/entries/{entry['entry_id']}",
        json={
            "decision": "approved",
            "corrected_answer": "4",
            "note": "Verified against the official source.",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["decision"] == "approved"
    assert data["corrected_answer"] == "4"
    assert data["note"] == "Verified against the official source."
    assert data["reviewed_at"]


def test_answer_key_entry_can_be_rejected(client):
    conversion_id = upload_with_answer_key(client)

    entry = client.get("/api/answer-keys").json()["items"][0]

    response = client.patch(
        f"/api/answer-keys/{conversion_id}/entries/{entry['entry_id']}",
        json={
            "decision": "rejected",
            "note": "Source answer needs verification.",
        },
    )

    assert response.status_code == 200
    assert response.json()["decision"] == "rejected"

    rejected = client.get(
        "/api/answer-keys",
        params={"decision": "rejected"},
    )

    assert rejected.status_code == 200
    assert rejected.json()["total"] == 1


def test_answer_keys_support_decision_filter(client):
    conversion_id = upload_with_answer_key(client)

    entries = client.get("/api/answer-keys").json()["items"]

    response = client.patch(
        f"/api/answer-keys/{conversion_id}/entries/{entries[0]['entry_id']}",
        json={"decision": "approved"},
    )

    assert response.status_code == 200

    approved = client.get(
        "/api/answer-keys",
        params={"decision": "approved"},
    )

    pending = client.get(
        "/api/answer-keys",
        params={"decision": "pending"},
    )

    assert approved.json()["total"] == 1
    assert pending.json()["total"] == 1


def test_answer_key_decision_does_not_modify_extraction_result(client):
    conversion_id = upload_with_answer_key(client)

    original_job = read_job(conversion_id)
    original_result = original_job["result"].copy()

    entry = original_job["answer_key"]["entries"][0]

    response = client.patch(
        f"/api/answer-keys/{conversion_id}/entries/{entry['entry_id']}",
        json={
            "decision": "approved",
            "corrected_answer": "4",
            "note": "Manual correction.",
        },
    )

    assert response.status_code == 200

    updated_job = read_job(conversion_id)

    assert updated_job["result"] == original_result
    assert updated_job["answer_key"]["entries"][0]["answer"] == entry["answer"]

    result_file = (
        settings.storage_path
        / conversion_id
        / "result.json"
    )

    exported_result = json.loads(
        result_file.read_text(encoding="utf-8")
    )

    assert exported_result == original_result


def test_answer_key_decision_rejects_missing_conversion(client):
    response = client.patch(
        "/api/answer-keys/missing/entries/missing-entry",
        json={"decision": "approved"},
    )

    assert response.status_code == 404


def test_answer_key_decision_rejects_missing_entry(client):
    conversion_id = upload_with_answer_key(client)

    response = client.patch(
        f"/api/answer-keys/{conversion_id}/entries/missing-entry",
        json={"decision": "approved"},
    )

    assert response.status_code == 404


def test_answer_key_decision_rejects_invalid_decision(client):
    conversion_id = upload_with_answer_key(client)

    entry = client.get("/api/answer-keys").json()["items"][0]

    response = client.patch(
        f"/api/answer-keys/{conversion_id}/entries/{entry['entry_id']}",
        json={"decision": "pending"},
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("params", "expected_status"),
    [
        ({"limit": 0}, 422),
        ({"limit": 101}, 422),
        ({"offset": -1}, 422),
        ({"search": "x" * 201}, 422),
    ],
)
def test_answer_keys_reject_invalid_query_parameters(
    client,
    params,
    expected_status,
):
    response = client.get(
        "/api/answer-keys",
        params=params,
    )

    assert response.status_code == expected_status 


def test_publish_creates_first_version(client):
    conversion_id = upload_with_answer_key(client)

    job = read_job(conversion_id)

    for section in job["result"]["sections"]:
        for question in section["questions"]:
            question["review_required"] = False

    update_job(conversion_id, result=job["result"])

    entries = job["answer_key"]["entries"]

    for entry in entries:
        update_job(
            conversion_id,
            answer_key_decisions={
                **read_job(conversion_id).get("answer_key_decisions", {}),
                entry["entry_id"]: {
                    "decision": "approved",
                    "corrected_answer": None,
                    "note": None,
                    "reviewed_at": "2026-11-14T00:00:00+00:00",
                },
            },
        )

    response = client.post(
        f"/api/conversions/{conversion_id}/publish"
    )

    assert response.status_code == 200

    publication = response.json()

    assert publication["version"] == 1
    assert publication["total_questions"] == 2
    assert publication["publication_id"] == f"{conversion_id}-v1"


def test_publish_creates_immutable_versions(client):
    conversion_id = upload_with_answer_key(client)

    job = read_job(conversion_id)

    for section in job["result"]["sections"]:
        for question in section["questions"]:
            question["review_required"] = False

    update_job(conversion_id, result=job["result"])

    for entry in job["answer_key"]["entries"]:
        current = read_job(conversion_id)
        decisions = current.get("answer_key_decisions", {})
        decisions[entry["entry_id"]] = {
            "decision": "approved",
            "corrected_answer": None,
            "note": None,
            "reviewed_at": "2026-11-14T00:00:00+00:00",
        }
        update_job(conversion_id, answer_key_decisions=decisions)

    first = client.post(
        f"/api/conversions/{conversion_id}/publish"
    )
    assert first.status_code == 200

    second = client.post(
        f"/api/conversions/{conversion_id}/publish"
    )
    assert second.status_code == 200

    assert first.json()["version"] == 1
    assert second.json()["version"] == 2

    history = client.get(
        f"/api/conversions/{conversion_id}/publications"
    )

    assert history.status_code == 200
    assert history.json()["total"] == 2


def test_publish_rejects_unreviewed_questions(client):
    conversion_id = upload_with_answer_key(client)

    response = client.post(
        f"/api/conversions/{conversion_id}/publish"
    )

    assert response.status_code == 409


def test_publish_does_not_modify_original_result(client):
    conversion_id = upload_with_answer_key(client)

    original = read_job(conversion_id)["result"]

    client.post(
        f"/api/conversions/{conversion_id}/publish"
    )

    updated = read_job(conversion_id)["result"]

    assert updated == original

    result_file = (
        settings.storage_path
        / conversion_id
        / "result.json"
    )

    exported = json.loads(
        result_file.read_text(encoding="utf-8")
    )

    assert exported == original


def test_get_missing_publication_returns_404(client):
    conversion_id = upload_with_answer_key(client)

    response = client.get(
        f"/api/conversions/{conversion_id}/publications/1"
    )

    assert response.status_code == 404

def prepare_publishable_conversion(client):
    conversion_id = upload_with_answer_key(client)
    job = read_job(conversion_id)

    for section in job["result"]["sections"]:
        for question in section["questions"]:
            question["review_required"] = False

    decisions = {}

    for entry in job["answer_key"]["entries"]:
        decisions[entry["entry_id"]] = {
            "decision": "approved",
            "corrected_answer": None,
            "note": None,
            "reviewed_at": "2026-11-14T00:00:00+00:00",
        }

    update_job(
        conversion_id,
        result=job["result"],
        answer_key_decisions=decisions,
    )

    return conversion_id

def test_rejected_question_is_excluded_from_publication(client):
    conversion_id = prepare_publishable_conversion(client)
    job = read_job(conversion_id)

    first_entry = job["answer_key"]["entries"][0]
    rejected_question_id = first_entry["matched_question_id"]

    update_job(
        conversion_id,
        review_decisions={
            rejected_question_id: {
                "decision": "rejected",
                "note": "Incorrect extraction.",
                "reviewed_at": "2026-11-14T00:00:00+00:00",
            }
        },
    )

    response = client.post(
        f"/api/conversions/{conversion_id}/publish"
    )

    assert response.status_code == 200

    publication = response.json()
    published_ids = {
        question["question_id"]
        for question in publication["questions"]
    }

    assert rejected_question_id not in published_ids
    assert publication["total_questions"] == 1

def test_approved_answer_key_correction_is_published(client):
    conversion_id = prepare_publishable_conversion(client)
    job = read_job(conversion_id)

    entry = job["answer_key"]["entries"][0]

    decisions = job["answer_key_decisions"]
    decisions[entry["entry_id"]]["corrected_answer"] = "4"

    update_job(
        conversion_id,
        answer_key_decisions=decisions,
    )

    response = client.post(
        f"/api/conversions/{conversion_id}/publish"
    )

    assert response.status_code == 200

    publication = response.json()

    question = next(
        question
        for question in publication["questions"]
        if question["question_id"] == entry["matched_question_id"]
    )

    assert question["correct_answer"] == "4"

def test_invalid_answer_key_correction_excludes_question(client):
    conversion_id = prepare_publishable_conversion(client)
    job = read_job(conversion_id)

    entry = job["answer_key"]["entries"][0]

    decisions = job["answer_key_decisions"]
    decisions[entry["entry_id"]]["corrected_answer"] = "999"

    update_job(
        conversion_id,
        answer_key_decisions=decisions,
    )

    response = client.post(
        f"/api/conversions/{conversion_id}/publish"
    )

    assert response.status_code == 200

    publication = response.json()

    published_ids = {
        question["question_id"]
        for question in publication["questions"]
    }

    assert entry["matched_question_id"] not in published_ids
    assert publication["total_questions"] == 1

def test_documents_list_only_returns_authenticated_organizations_jobs(
    client,
):
    organization_a_upload = upload(client, "organization-a.txt")

    assert organization_a_upload.status_code == 200

    organization_a_id = organization_a_upload.json()["conversion_id"]

    organization_b_id, _ = create_job(
        organization_id="org-b",
        created_by="user-b",
    )

    listing = client.get("/api/documents")

    assert listing.status_code == 200

    data = listing.json()
    conversion_ids = {
        item["conversion_id"]
        for item in data["items"]
    }

    assert data["total"] == 1
    assert organization_a_id in conversion_ids
    assert organization_b_id not in conversion_ids

def test_other_organization_cannot_access_document_status(client):
    organization_a_upload = upload(client, "organization-a.txt")

    assert organization_a_upload.status_code == 200

    organization_a_id = organization_a_upload.json()["conversion_id"]

    response = client.get(
        f"/api/conversions/{organization_a_id}"
    )

    assert response.status_code == 200

    original_principal = app.dependency_overrides[get_current_principal]

    app.dependency_overrides[get_current_principal] = lambda: (
        AuthenticatedPrincipal(
            user_id="user-b",
            organization_id="org-b",
            role="owner",
        )
    )

    try:
        response = client.get(
            f"/api/conversions/{organization_a_id}"
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Conversion not found."

    finally:
        app.dependency_overrides[get_current_principal] = original_principal

def test_other_organization_cannot_download_or_delete_document(client):
    upload_response = upload(client, "organization-a.txt")

    assert upload_response.status_code == 200

    conversion_id = upload_response.json()["conversion_id"]

    root = settings.storage_path / conversion_id
    media_dir = root / "media"
    media_dir.mkdir(exist_ok=True)
    (media_dir / "private.png").write_bytes(b"private media")

    original_principal = app.dependency_overrides[get_current_principal]

    app.dependency_overrides[get_current_principal] = lambda: (
        AuthenticatedPrincipal(
            user_id="user-b",
            organization_id="org-b",
            role="owner",
        )
    )

    try:
        assert client.get(
            f"/api/conversions/{conversion_id}/json"
        ).status_code == 404

        assert client.get(
            f"/api/conversions/{conversion_id}/zip"
        ).status_code == 404

        assert client.get(
            f"/api/conversions/{conversion_id}/media/private.png"
        ).status_code == 404

        delete_response = client.delete(
            f"/api/conversions/{conversion_id}"
        )

        assert delete_response.status_code == 404
        assert root.exists()

    finally:
        app.dependency_overrides[get_current_principal] = original_principal

def test_other_organization_cannot_view_or_update_review_question(client):
    response = upload(
        client,
        "review-private.txt",
        b"1. What is photosynthesis?\n"
        b"A. Respiration\n"
        b"B. Food production in plants\n"
        b"C. Digestion\n"
        b"D. Transpiration",
    )
    assert response.status_code == 200

    conversion_id = response.json()["conversion_id"]
    job = read_job(conversion_id)

    question = next(
        question
        for section in job["result"]["sections"]
        for question in section["questions"]
    )

    question["review_required"] = True
    update_job(conversion_id, result=job["result"])

    original_principal = app.dependency_overrides[get_current_principal]

    app.dependency_overrides[get_current_principal] = lambda: (
        AuthenticatedPrincipal(
            user_id="user-b",
            organization_id="org-b",
            role="owner",
        )
    )

    try:
        listing = client.get("/api/review/questions")

        assert listing.status_code == 200
        assert listing.json()["total"] == 0

        decision = client.patch(
            f"/api/review/questions/{conversion_id}/{question['question_id']}",
            json={
                "decision": "approved",
                "note": "Unauthorized review attempt.",
            },
        )

        assert decision.status_code == 404

        stored_job = read_job(conversion_id)
        assert question["question_id"] not in stored_job.get(
            "review_decisions", {}
        )

    finally:
        app.dependency_overrides[get_current_principal] = original_principal

def test_other_organization_cannot_view_or_update_answer_key(client):
    conversion_id = upload_with_answer_key(client)

    listing = client.get("/api/answer-keys")
    assert listing.status_code == 200

    entry = listing.json()["items"][0]
    entry_id = entry["entry_id"]

    original_principal = app.dependency_overrides[get_current_principal]

    app.dependency_overrides[get_current_principal] = lambda: (
        AuthenticatedPrincipal(
            user_id="user-b",
            organization_id="org-b",
            role="owner",
        )
    )

    try:
        response = client.get("/api/answer-keys")

        assert response.status_code == 200
        assert response.json()["total"] == 0

        response = client.patch(
            f"/api/answer-keys/{conversion_id}/entries/{entry_id}",
            json={
                "decision": "approved",
                "corrected_answer": "4",
                "note": "Unauthorized correction.",
            },
        )

        assert response.status_code == 404

    finally:
        app.dependency_overrides[get_current_principal] = original_principal

def test_other_organization_cannot_view_or_create_publications(client):
    response = upload(
        client,
        "publish-private.txt",
        b"1. What is photosynthesis?\n"
        b"A. Respiration\n"
        b"B. Food production in plants\n"
        b"C. Digestion\n"
        b"D. Transpiration",
    )
    assert response.status_code == 200

    conversion_id = response.json()["conversion_id"]

    publish_response = client.post(
        f"/api/conversions/{conversion_id}/publish"
    )
    assert publish_response.status_code == 200

    original_principal = app.dependency_overrides[get_current_principal]

    app.dependency_overrides[get_current_principal] = lambda: (
        AuthenticatedPrincipal(
            user_id="user-b",
            organization_id="org-b",
            role="owner",
        )
    )

    try:
        response = client.get(
            f"/api/conversions/{conversion_id}/publications"
        )
        assert response.status_code == 404

        response = client.get(
            f"/api/conversions/{conversion_id}/publications/1"
        )
        assert response.status_code == 404

        response = client.post(
            f"/api/conversions/{conversion_id}/publish"
        )
        assert response.status_code == 404

    finally:
        app.dependency_overrides[get_current_principal] = original_principal

def test_other_organization_cannot_view_questions(client):
    response = upload(
        client,
        "private-questions.txt",
        b"1. What is photosynthesis?\n"
        b"A. Respiration\n"
        b"B. Food production in plants\n"
        b"C. Digestion\n"
        b"D. Transpiration",
    )
    assert response.status_code == 200

    original_principal = app.dependency_overrides[get_current_principal]

    app.dependency_overrides[get_current_principal] = lambda: (
        AuthenticatedPrincipal(
            user_id="user-b",
            organization_id="org-b",
            role="owner",
        )
    )

    try:
        listing = client.get("/api/questions")

        assert listing.status_code == 200
        assert listing.json()["total"] == 0
        assert listing.json()["items"] == []

    finally:
        app.dependency_overrides[get_current_principal] = original_principal

def test_analytics_only_includes_authenticated_organization(client):
    own_upload = upload(
        client,
        "organization-a.txt",
        b"1. What is photosynthesis?\n"
        b"A. Respiration\n"
        b"B. Food production in plants\n"
        b"C. Digestion\n"
        b"D. Transpiration",
    )
    assert own_upload.status_code == 200

    other_conversion_id, _ = create_job(
        organization_id="org-b",
        created_by="user-b",
    )

    original_principal = app.dependency_overrides[get_current_principal]

    try:
        organization_a = client.get("/api/analytics/overview")
        assert organization_a.status_code == 200
        assert organization_a.json()["documents"]["total"] == 1

        app.dependency_overrides[get_current_principal] = lambda: (
            AuthenticatedPrincipal(
                user_id="user-b",
                organization_id="org-b",
                role="owner",
            )
        )

        organization_b = client.get("/api/analytics/overview")
        assert organization_b.status_code == 200
        assert organization_b.json()["documents"]["total"] == 1

        assert (
            organization_a.json()["recent_documents"][0]["conversion_id"]
            != other_conversion_id
        )

    finally:
        app.dependency_overrides[get_current_principal] = original_principal