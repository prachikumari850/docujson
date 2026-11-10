import io
import json
import re
import zipfile
from pathlib import Path

import pytest
import fitz
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


def test_supplied_srg_paper_and_key_regression(tmp_path, monkeypatch):
    downloads = Path.home() / "Downloads"
    paper = downloads / "SRG TEST-01 (PHYSICS) 03 AUG QP.pdf"
    key = downloads / "answer.pdf"
    if not paper.is_file() or not key.is_file():
        storage = Path(__file__).resolve().parents[2] / "storage" / ".audit-real-current"
        candidates = list(storage.glob("**/input_0.pdf"))
        for candidate in candidates:
            paired_key = candidate.with_name("input_1.pdf")
            if not paired_key.is_file():
                continue
            try:
                with fitz.open(candidate) as paper_doc, fitz.open(paired_key) as key_doc:
                    if len(paper_doc) == 16 and len(key_doc) == 7:
                        paper, key = candidate, paired_key
                        break
            except Exception:
                continue
    if not paper.is_file() or not key.is_file():
        pytest.skip("Supplied SRG source PDFs are not available in Downloads or the preserved audit storage.")

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

        # These expectations are transcribed from the rendered source page 4.
        # Keep the vector regression ahead of unrelated legacy assertions so
        # failures identify whether mark ownership or option grouping regressed.
        q7 = by_number[7]
        q7_stem = q7["question"]["en"] or ""
        assert all(vector in q7_stem for vector in ("a⃗", "b⃗", "c⃗"))
        q7_options = {option["id"]: option["text"] for option in q7["options"]}
        assert set(q7_options) == {"1", "2", "3", "4"}
        assert "a⃗ + b⃗" in q7_options["1"]
        assert "a⃗ − b⃗" in q7_options["2"]
        assert "can be zero" in q7_options["3"]
        assert "cannot be zero" in q7_options["4"]

        q8_options = {option["id"]: re.sub(r"\s+", "", option["text"]) for option in by_number[8]["options"]}
        assert q8_options == {
            "1": "a⃗+b⃗=2c⃗", "2": "a⃗+b⃗=c⃗",
            "3": "a⃗−b⃗=2c⃗", "4": "a⃗−b⃗=c⃗",
        }

        # Page 5 statements use vector arrows in the source and are adjacent to
        # bilingual columns; they must remain within Q14 rather than Q13/Q15.
        q14_text = by_number[14]["question"]["en"] or ""
        assert "Statement-I" in q14_text
        assert "A⃗ × B⃗" in q14_text
        assert "A⃗ − B⃗" in q14_text

        q39_text = by_number[39]["question"]["en"] or ""
        for source_expression in (
            "2î + 2ĵ −2k̂", "5î + yĵ + k̂", "−î + 2ĵ + 2k̂",
        ):
            assert source_expression.replace(" ", "") in q39_text.replace(" ", "")

        assert result["document"]["total_pages"] == 16
        assert len(questions) == 50
        assert [len(section["questions"]) for section in result["sections"]] == [35, 15]
        assert result["document"]["answer_key_extracted"] == 50
        assert result["document"]["answer_key_matched"] == 50
        assert by_number[13]["correct_answer"] == "1"
        assert by_number[17]["correct_answer"] == "2"
        assert "t²" in (by_number[3]["question"]["en"] or "")
        assert "eᵗ" in (by_number[3]["question"]["en"] or "")
        option_3_2 = next(option for option in by_number[3]["options"] if option["id"] == "2")
        compact_option_3_2 = re.sub(r"\s+", "", option_3_2["text"])
        assert compact_option_3_2 == "t³/3−eᵗ+1/t"
        q4_options = {option["id"]: option for option in by_number[4]["options"]}
        compact_q4_option1 = re.sub(r"\s+", "", q4_options["1"]["text"])
        compact_q4_option2 = re.sub(r"\s+", "", q4_options["2"]["text"])
        assert "2/5(x)⁵⁄²+c" in compact_q4_option1
        assert "x²/2" not in compact_q4_option1
        assert "x²/2" in compact_q4_option2
        assert "2/5(x)⁵⁄²+c" in compact_q4_option2
        assert "π/4" not in "".join(option["text"] for option in by_number[4]["options"])
        assert "π/4" in (by_number[5]["original_text"] or "")
        assert "π/4" in (by_number[5]["question"]["en"] or "")
        assert "∫" in (by_number[5]["question"]["en"] or "")
        assert q4_options["2"]["source"]["bbox"][0] < 300
        assert by_number[26]["review_required"] is False
        assert "In the locus diagrams" in (by_number[26]["question"]["en"] or "")
        assert "Hindi + English" not in (by_number[26]["question"]["en"] or "")
        assert "x²" in (by_number[6]["question"]["en"] or "")
        assert all(question.get("extraction_confidence") is None for question in questions)
        assert all(question["confidence"].get("mathematical_reconstruction") is None for question in questions)
        assert "3a" in (by_number[13]["question"]["en"] or "")
        assert by_number[13]["options"][0]["text"].startswith("cos")
        assert "1/11" in by_number[13]["options"][0]["text"]
        assert by_number[13]["options"][1]["text"].strip() == "60°"
        assert "यदि" in (by_number[13]["question"]["hi"] or "")
        assert all("d2y" not in option["text"] for option in by_number[36]["options"])
        assert "d²y/dx²" in (by_number[37]["question"]["en"] or "")
        assert all(option["media"] for option in by_number[17]["options"])
        # Legacy font/vector formula choices that native extraction misses must
        # retain a source-cell crop, not a crop of only the printed option label.
        for number, option_ids in ((8, {"3", "4"}), (9, {"3", "4"})):
            for option in by_number[number]["options"]:
                if option["id"] in option_ids:
                    crops = [asset for asset in option["media"] if asset["type"] == "option_crop"]
                    assert crops, f"Q{number} option {option['id']} has no source formula crop"
                    assert fitz.Rect(crops[0]["bbox"]).width > 35
        q24_option4 = next(option for option in by_number[24]["options"] if option["id"] == "4")
        q24_crops = [asset for asset in q24_option4["media"] if asset["type"] == "option_crop"]
        assert q24_crops
        assert fitz.Rect(q24_crops[0]["bbox"]).height >= 40
        q43 = by_number[43]
        q43_option1 = next(option for option in q43["options"] if option["id"] == "1")
        q43_option3 = next(option for option in q43["options"] if option["id"] == "3")
        q43_crops = [asset for asset in q43_option1["media"] if asset["type"] == "option_crop"]
        assert q43_crops
        assert q43_option1["review_required"] is True
        assert fitz.Rect(q43_crops[0]["bbox"]).y1 <= q43_option3["source"]["bbox"][1] - 5
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
            assert "media/manifest.json" in archive_names
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
            manifest = json.loads(archive.read("media/manifest.json"))
            assert all(f"media/{asset['filename']}" in archive_names for asset in manifest["assets"])

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
