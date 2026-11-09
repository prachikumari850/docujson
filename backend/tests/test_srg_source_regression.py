import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def test_supplied_srg_paper_and_key_regression(tmp_path, monkeypatch):
    downloads = Path.home() / "Downloads"
    paper = downloads / "SRG TEST-01 (PHYSICS) 03 AUG QP.pdf"
    key = downloads / "answer.pdf"
    if not paper.is_file() or not key.is_file():
        pytest.skip("Supplied SRG source PDFs are not available in the user Downloads folder.")

    monkeypatch.setattr(settings, "storage_dir", str(tmp_path / "storage"))
    roles = {paper.name: "question_paper", key.name: "answer_key"}
    files = [
        ("files", (paper.name, paper.read_bytes(), "application/pdf")),
        ("files", (key.name, key.read_bytes(), "application/pdf")),
    ]
    with TestClient(app) as client:
        response = client.post("/api/convert", files=files, data={"roles": json.dumps(roles)})
        assert response.status_code == 200, response.text
        conversion_id = response.json()["conversion_id"]
        status = client.get(f"/api/conversions/{conversion_id}")
        assert status.status_code == 200, status.text
        payload = status.json()
        assert payload["status"] == "completed", payload.get("error")
        result = payload["result"]
        questions = [question for section in result["sections"] for question in section["questions"]]
        by_number = {int(question["question_number"]): question for question in questions}

        assert result["document"]["total_pages"] == 16
        assert len(questions) == 50
        assert [len(section["questions"]) for section in result["sections"]] == [35, 15]
        assert result["document"]["answer_key_extracted"] == 50
        assert result["document"]["answer_key_matched"] == 50
        assert by_number[13]["correct_answer"] == "1"
        assert by_number[17]["correct_answer"] == "2"
        assert "3a" in (by_number[13]["question"]["en"] or "")
        assert by_number[13]["options"][0]["text"].startswith("cos")
        assert "1/11" in by_number[13]["options"][0]["text"]
        assert by_number[13]["options"][1]["text"].strip() == "60°"
        assert "यदि" in (by_number[13]["question"]["hi"] or "")
        assert all("d2y" not in option["text"] for option in by_number[36]["options"])
        assert "d2y/dx2" in (by_number[37]["question"]["en"] or "")
        assert all(option["media"] for option in by_number[17]["options"])
        assert by_number[36]["media"] and by_number[37]["media"]
        assert all(
            not any(marker in (question.get("original_text") or "") for marker in ("Telegram", "PHASE", "NEETxNOAH"))
            for question in questions
        )

        options = [option for question in questions for option in question["options"]]
        media_backed = sum(bool(option["media"]) for option in options)
        unresolved = sum(not option["text"].strip() and not option["media"] for option in options)
        assert all(option["text"].strip() or option["media"] or option["review_required"] for option in options)

        json_response = client.get(f"/api/conversions/{conversion_id}/json")
        zip_response = client.get(f"/api/conversions/{conversion_id}/zip")
        assert json_response.status_code == 200
        assert zip_response.status_code == 200
        assert json.loads(json_response.content)["document"]["total_questions"] == 50
        with zipfile.ZipFile(io.BytesIO(zip_response.content)) as archive:
            assert archive.testzip() is None
            archive_names = set(archive.namelist())
            referenced = [
                media["filename"]
                for question in questions
                for media in question["media"]
            ] + [
                media["filename"]
                for option in options
                for media in option["media"]
            ]
            assert all(f"media/{filename}" in archive_names for filename in referenced)
            assert "debug/extraction_debug.json" in archive_names

        print(json.dumps({
            "pages": result["document"]["total_pages"],
            "questions": len(questions),
            "sections": [len(section["questions"]) for section in result["sections"]],
            "text_options": sum(bool(option["text"].strip()) for option in options),
            "image_backed_options": media_backed,
            "incomplete_options": unresolved,
            "review_questions": sum(bool(question["review_required"]) for question in questions),
            "answer_key_extracted": result["document"]["answer_key_extracted"],
            "answer_key_matched": result["document"]["answer_key_matched"],
            "q13": by_number[13]["correct_answer"],
            "q17": by_number[17]["correct_answer"],
            "json_download": json_response.status_code,
            "zip_download": zip_response.status_code,
            "zip_integrity": "valid",
            "media_references": len(referenced),
        }, ensure_ascii=True))
