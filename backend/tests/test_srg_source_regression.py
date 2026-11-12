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
        vector = "\u20d7"
        assert q7_stem.index(f"c{vector}") < q7_stem.index(":-")
        assert all(vector in q7_stem for vector in ("a⃗", "b⃗", "c⃗"))
        q7_options = {option["id"]: option["text"] for option in q7["options"]}
        assert set(q7_options) == {"1", "2", "3", "4"}
        assert "a⃗ + b⃗" in q7_options["1"]
        assert "a⃗ − b⃗" in q7_options["2"]
        assert "can be zero" in q7_options["3"]
        assert "cannot be zero" in q7_options["4"]

        # Q2's graph is an embedded raster; its canonical PNG remains the
        # directly displayable and downloadable asset beside any SVG wrapper.
        q2_graph = next(media for media in by_number[2]["media"] if media["filename"] == "p3_img1.png")
        assert q2_graph["source_page"] == 3
        assert q2_graph["pixel_width"] > 0 and q2_graph["pixel_height"] > 0
        assert q2_graph["representation"] == "svg_wrapper"
        assert q2_graph["svg_genuine_vector"] is False
        assert "raster" in q2_graph["svg_fallback_reason"].lower()
        graph_response = client.get(f"/api/conversions/{conversion_id}/media/{q2_graph['filename']}")
        assert graph_response.status_code == 200
        assert graph_response.headers["content-type"].startswith("image/png")

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
        assert "t\u00b2" in (by_number[3]["question"]["hi"] or "")
        compact_option_3_2 = re.sub(r"\s+", "", option_3_2["text"])
        assert compact_option_3_2 == "t³/3−eᵗ+1/t"
        math_summary = result["document"]["math_extraction"]
        assert math_summary["method"] == "pymupdf_geometry_ir"
        assert math_summary["assigned"] > 0
        assert math_summary["unassigned"] == len(math_summary["unassigned_fragments"])
        assert sum(math_summary["unassigned_reasons"].values()) == math_summary["unassigned"]
        assert all(fragment["reason"] and fragment["atom_ids"] for fragment in math_summary["unassigned_fragments"])
        assert option_3_2["math_evidence"]
        assert len(option_3_2["math_evidence"]) == 2
        assert len({tuple(item["source_bbox"]) for item in option_3_2["math_evidence"]}) == 2
        assert all(item["source_page"] == option_3_2["source"]["page"] for item in option_3_2["math_evidence"])
        assert all(item["atom_ids"] for item in option_3_2["math_evidence"])
        assert all(item["latex"] is None or item["review_required"] is False for item in option_3_2["math_evidence"])
        assert any(
            item["extraction_method"] == "pymupdf_geometry_ir"
            and item["latex"] == r"\frac{t^{3}}{3}-e^{t}+\frac{1}{t}"
            for item in option_3_2["math_evidence"]
        )
        assert any(
            box[0] > 400
            for region in option_3_2["source"].get("alternate_content_bboxes", [])
            if region.get("page") == 3
            for box in [region["bbox"]]
        )
        q4_options = {option["id"]: option for option in by_number[4]["options"]}
        assert all(len(option["math_evidence"]) == 2 for option in q4_options.values() if option["text"].strip())
        assert all(option["source"]["content_bboxes"] for option in q4_options.values())
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
        assert "Find the value of" in (by_number[5]["question"]["en"] or "")
        assert "∫₀^{π/4}" in (by_number[5]["question"]["en"] or "")
        q5_integrals = [item for item in by_number[5]["math_evidence"] if item["extraction_method"] == "native_span_geometry_integral_limit_association"]
        assert q5_integrals
        assert all(item["latex"] == r"\int_{0}^{\pi/4}(\cos x-\sin x)\,dx" and item["review_required"] is False for item in q5_integrals)
        # Q5's four radical choices are native PDF text in the bounded option
        # cells; the option crop remains downloadable as expandable evidence.
        q5_options = {option["id"]: option for option in by_number[5]["options"]}
        assert all(option["text"].strip() for option in q5_options.values())
        assert "√2" in q5_options["1"]["text"] and "−1" in q5_options["1"]["text"]
        assert "√2" in q5_options["2"]["text"] and "+ 1" in q5_options["2"]["text"]
        assert re.sub(r"\s+", "", q5_options["3"]["text"]) == "1−√2"
        assert re.sub(r"\s+", "", q5_options["4"]["text"]) == "−√2−1"
        assert q4_options["2"]["source"]["bbox"][0] < 300
        vector = "\u20d7"
        q9_en = by_number[9]["question"]["en"] or ""
        q9_hi = by_number[9]["question"]["hi"] or ""
        assert f"If A{vector} = B{vector} + C{vector} and" in q9_en
        assert f"between A{vector} and C{vector} is" in q9_en
        assert f"A{vector} = B{vector} + C{vector}" in q9_hi
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
        q17_crops = {
            option["id"]: fitz.Rect(next(asset for asset in option["media"] if asset["type"] == "option_crop")["bbox"])
            for option in by_number[17]["options"]
        }
        assert all(q17_crops[str(index)].x1 <= q17_crops[str(index + 1)].x0 for index in range(1, 4))
        # These arrow choices are raster-backed in the supplied page. A
        # page-border line crossing option 4 must not create a fake vector SVG.
        assert all(
            next(asset for asset in option["media"] if asset["type"] == "option_crop")["representation"] == "svg_wrapper"
            for option in by_number[17]["options"]
        )
        q17_option4_crop = next(
            asset for asset in by_number[17]["options"][3]["media"]
            if asset["type"] == "option_crop"
        )
        with fitz.open(paper) as source_pdf:
            option4_cell = fitz.Rect(q17_option4_crop["bbox"])
            option4_images = [
                fitz.Rect(item["bbox"])
                for item in source_pdf[5].get_image_info(xrefs=True)
                if option4_cell.contains(
                    fitz.Point(
                        (item["bbox"][0] + item["bbox"][2]) / 2,
                        (item["bbox"][1] + item["bbox"][3]) / 2,
                    )
                )
                or (
                    fitz.Rect(item["bbox"]).width < 20
                    and fitz.Rect(item["bbox"]).height < 60
                    and abs((item["bbox"][0] + item["bbox"][2]) / 2 - (option4_cell.x0 + option4_cell.x1) / 2) < 18
                    and option4_cell.y0 - 12 <= (item["bbox"][1] + item["bbox"][3]) / 2 <= option4_cell.y1 + 12
                )
            ]
        assert option4_images, "Q17 option 4 source arrow image must be found in the PDF geometry"
        assert all(option4_cell.contains(rect) for rect in option4_images), "Option crop must include complete embedded arrow image bounds"
        # Legacy font/vector formula choices that native extraction misses must
        # retain a source-cell crop, not a crop of only the printed option label.
        for number, option_ids in ((8, {"3", "4"}), (9, {"3", "4"})):
            for option in by_number[number]["options"]:
                if option["id"] in option_ids:
                    crops = [asset for asset in option["media"] if asset["type"] == "option_crop"]
                    assert crops, f"Q{number} option {option['id']} has no source formula crop"
                    assert fitz.Rect(crops[0]["bbox"]).width > 35
        # Crops for options on the same horizontal row use disjoint cell
        # bounds. In particular, Q9 option 2 must not begin inside option 1.
        q9_crops = {
            option["id"]: fitz.Rect(next(asset for asset in option["media"] if asset["type"] == "option_crop")["bbox"])
            for option in by_number[9]["options"][:2]
        }
        assert q9_crops["1"].x1 <= q9_crops["2"].x0
        assert q9_crops["1"].width >= 90
        assert q9_crops["2"].width >= 65
        assert by_number[9]["options"][0]["review_required"] is True
        assert all(
            asset["representation"] == "svg_vector" and asset["svg_genuine_vector"] is True
            for option in by_number[9]["options"][:2]
            for asset in option["media"]
            if asset["type"] == "option_crop"
        )
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
            all_media = [media for question in questions for media in question["media"]]
            all_media.extend(media for option in options for media in option["media"])
            wrappers = [media for media in all_media if media.get("svg_filename")]
            assert wrappers
            assert all(
                asset.get("svg_fallback_reason")
                for asset in all_media
                if asset.get("representation") != "svg_vector"
            )
            for asset in wrappers:
                assert asset["representation"] in {"svg_wrapper", "svg_vector"}
                if asset["representation"] == "svg_vector":
                    assert asset["media_format"] == "svg_vector"
                    assert asset["svg_genuine_vector"] is True
                else:
                    assert asset["media_format"] == "svg_raster_wrapper"
                    assert asset["svg_genuine_vector"] is False
            referenced.extend(media["svg_filename"] for media in wrappers)
            math_crops = [
                item["source_crop_filename"]
                for question in questions
                for item in question.get("math_evidence", [])
                if item.get("source_crop_filename")
            ] + [
                item["source_crop_filename"]
                for option in options
                for item in option.get("math_evidence", [])
                if item.get("source_crop_filename")
            ]
            referenced.extend(math_crops)
            assert all(f"media/{filename}" in archive_names for filename in referenced)
            assert all(f"media/{media['filename']}" in archive_names for media in wrappers)
            assert all(media["relative_path"] in archive_names for media in all_media)
            assert all(media["svg_relative_path"] in archive_names for media in wrappers)
            import xml.etree.ElementTree as ET
            for asset in wrappers:
                svg_root = ET.fromstring(archive.read(f"media/{asset['svg_filename']}"))
                assert svg_root.tag == "{http://www.w3.org/2000/svg}svg"
                if asset["representation"] == "svg_vector":
                    assert svg_root.find(".//{http://www.w3.org/2000/svg}path") is not None
                    assert svg_root.find(".//{http://www.w3.org/2000/svg}image") is None
                else:
                    assert svg_root.find(".//{http://www.w3.org/2000/svg}image") is not None
            assert "debug/extraction_debug.json" in archive_names
            manifest = json.loads(archive.read("media/manifest.json"))
            assert all(f"media/{asset['filename']}" in archive_names for asset in manifest["assets"])
            extraction_debug = json.loads(archive.read("debug/extraction_debug.json"))
            page3_debug = next(page for page in extraction_debug if page["page"] == 3)
            footer_tops = [
                row["bbox"][1]
                for row in page3_debug["span_lines"]
                if row["bbox"][1] > 600
                and re.search(r"(?i)PHASE|telegram|NEETxNOAH", row["text"])
            ]
            q5_option3_crop = next(
                media for media in by_number[5]["options"][2]["media"]
                if media["type"] == "option_crop"
            )
            assert footer_tops
            assert q5_option3_crop["bbox"][3] < min(footer_tops)

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
            "math_extraction": {key: value for key, value in math_summary.items() if key not in {"unassigned_fragments", "segmentation_issues"}},
            "math_evidence_items": sum(len(question.get("math_evidence", [])) for question in questions)
            + sum(len(option.get("math_evidence", [])) for option in options),
            "math_source_crops": len(math_crops),
            "unassigned_math_reason_counts": math_summary["unassigned_reasons"],
            "segmentation_issue_counts": {
                code: sum(issue["code"] == code for issue in math_summary.get("segmentation_issues", []))
                for code in sorted({issue["code"] for issue in math_summary.get("segmentation_issues", [])})
            },
        }, ensure_ascii=True))
