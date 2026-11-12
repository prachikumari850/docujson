import json

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.engine import classify_mcq_records, numbered_options


def _option(label, text="choice", media=None):
    return {
        "id": str(label),
        "text": text,
        "media": media or [],
        "source": {"page": 1, "bbox": [60, 100, 80, 112]},
    }


def _question(number, options, text="Choose the correct statement"):
    return {
        "question_id": f"q{number}",
        "question_number": number,
        "question": {"en": text, "hi": None},
        "question_type": "mcq",
        "options": options,
        "source": {"page": 1},
        "review_required": False,
        "review_reasons": [],
    }


def test_option_parser_supports_two_through_more_than_four_choices():
    for labels in (("1", "2"), ("1", "2", "3"), ("1", "2", "3", "4"), ("1", "2", "3", "4", "5", "6")):
        line = " ".join(f"({label}) value-{label}" for label in labels)
        assert [item["id"] for item in numbered_options(line)] == list(labels)
    assert [item["id"] for item in numbered_options("(A) alpha (B) beta (C) gamma (D) delta (E) epsilon")] == list("ABCDE")


def test_classification_confirms_variable_option_counts_and_image_only_choice():
    questions = [
        _question(1, [_option("1"), _option("2")]),
        _question(2, [_option("1"), _option("2"), _option("3")]),
        _question(3, [_option(str(i)) for i in range(1, 5)]),
        _question(4, [_option(str(i), "" if i == 2 else f"choice {i}", [{"filename": "choice.png"}] if i == 2 else []) for i in range(1, 6)]),
    ]
    exported, summary = classify_mcq_records([{"section_name": "A", "questions": questions}])
    assert [len(section["questions"]) for section in exported] == [4]
    assert [question["classification_status"] for question in exported[0]["questions"]] == ["confirmed_mcq"] * 4
    assert summary == {"parsed_records": 4, "confirmed_mcq": 4, "unresolved": 0, "excluded_non_mcq": 0, "debug_records": []}


def test_subjective_and_ambiguous_records_are_retained_only_in_debug():
    subjective = _question(2, [], "Explain the principle with a diagram")
    ambiguous = _question(3, [_option("1")])
    exported, summary = classify_mcq_records([{"section_name": "Section A", "questions": [subjective, ambiguous]}])
    assert exported == []
    assert subjective["classification_status"] == "excluded_non_mcq"
    assert ambiguous["classification_status"] == "unresolved"
    assert len(summary["debug_records"]) == 2
    assert all(row["classification_reasons"] for row in summary["debug_records"])


def test_upload_exports_only_confirmed_mcqs_and_zips_classification_debug(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "storage"))
    text = "\n".join([
        "SECTION A",
        "1. Choose the correct statement",
        "(1) first", "(2) second", "(3) third",
        "2. Explain the principle in detail",
        "3. Incomplete objective record", "(1) only one choice",
    ]).encode()
    with TestClient(app) as client:
        response = client.post("/api/convert", files={"files": ("paper.txt", text)})
        assert response.status_code == 200, response.text
        conversion_id = response.json()["conversion_id"]
        status = client.get(f"/api/conversions/{conversion_id}").json()
        assert status["status"] == "completed", status.get("error")
        result = status["result"]
        questions = [q for section in result["sections"] for q in section["questions"]]
        assert [q["question_number"] for q in questions] == [1]
        assert questions[0]["classification_status"] == "confirmed_mcq"
        assert result["document"]["question_classification"] == {
            "parsed_records": 3,
            "confirmed_mcq": 1,
            "unresolved": 1,
            "excluded_non_mcq": 1,
        }
        debug_path = settings.storage_path / conversion_id / "classification_debug.json"
        debug = json.loads(debug_path.read_text(encoding="utf-8"))
        assert {row["classification_status"] for row in debug["unresolved_and_excluded"]} == {"unresolved", "excluded_non_mcq"}
        json_response = client.get(f"/api/conversions/{conversion_id}/json")
        exported_json = json.loads(json_response.content)
        assert json_response.status_code == 200
        assert exported_json["sections"] == result["sections"]
        assert all(question["classification_status"] == "confirmed_mcq" for section in exported_json["sections"] for question in section["questions"])
        archive_response = client.get(f"/api/conversions/{conversion_id}/zip")
        assert archive_response.status_code == 200
        import io
        import zipfile
        with zipfile.ZipFile(io.BytesIO(archive_response.content)) as archive:
            assert "debug/classification_debug.json" in archive.namelist()
