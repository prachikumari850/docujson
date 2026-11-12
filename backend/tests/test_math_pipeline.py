import fitz

from app.services.math_pipeline import attach_math_evidence, page_math_segments, validate_segmentation


def _question(number, bbox, option_boxes=()):
    return {
        "question_id": f"q{number}",
        "question_number": number,
        "source": {"page": 1, "bbox": bbox, "content_bboxes": [{"page": 1, "bbox": bbox}]},
        "question": {"en": "stem", "hi": None},
        "math_evidence": [],
        "media": [],
        "options": [
            {
                "id": str(index),
                "text": "option",
                "source": {"page": 1, "bbox": box, "content_bboxes": [box]},
                "math_evidence": [],
                "media": [],
            }
            for index, box in enumerate(option_boxes, start=1)
        ],
    }


def _math_page_token(bbox, *, status="confirmed", latex=r"\frac{1}{2}", atom_ids=None):
    return {
        "page": 1,
        "column": "left",
        "baseline": bbox[3],
        "bbox": dict(zip(("x0", "y0", "x1", "y1"), bbox)),
        "tokens": [{
            "kind": "math",
            "text": "12",
            "bbox": dict(zip(("x0", "y0", "x1", "y1"), bbox)),
            "atom_ids": atom_ids or ["atom-1", "atom-2"],
            "unit_ids": ["unit-1"],
            "component_bboxes": [dict(zip(("x0", "y0", "x1", "y1"), bbox))],
            "latex": latex if status == "confirmed" else None,
            "status": status,
            "reasons": [] if status == "confirmed" else ["unit geometry is ambiguous"],
        }],
    }


def test_page_math_segments_preserve_order_atom_ids_and_component_boxes():
    document = fitz.open()
    page = document.new_page(width=220, height=100)
    page.insert_text((20, 50), "x", fontsize=12)
    page.insert_text((27, 43), "2", fontsize=7)
    rawdict = page.get_text("rawdict")
    segments = page_math_segments(page, 1, "fixture-fingerprint", rawdict, page.get_drawings(), page.get_image_info())
    document.close()

    assert segments
    tokens = [token for row in segments for token in row["tokens"]]
    assert all(token["atom_ids"] for token in tokens)
    assert any(token["kind"] == "math" for token in tokens)
    for token in tokens:
        if token["kind"] == "math":
            assert token["component_bboxes"]
            assert token["unit_ids"]
            assert token["bbox"]["x0"] <= token["bbox"]["x1"]


def test_math_fragment_is_owned_by_its_option_not_adjacent_question(tmp_path):
    document = fitz.open()
    document.new_page(width=200, height=220)
    question_one = _question(1, [0, 0, 120, 90], [[10, 35, 80, 50]])
    question_two = _question(2, [0, 110, 120, 200], [[10, 140, 80, 160]])
    sections = [{"section_name": "A", "questions": [question_one, question_two]}]
    page = {"page": 1, "ordered_segments": [_math_page_token([30, 38, 42, 46])]}

    result = attach_math_evidence(sections, [page], document, tmp_path)
    document.close()

    assert result["assigned"] == 1 and result["unassigned"] == 0
    assert question_one["options"][0]["math_evidence"][0]["latex"] == r"\frac{1}{2}"
    assert question_one["math_evidence"] == []
    assert question_two["options"][0]["math_evidence"] == []


def test_overlapping_option_regions_leave_math_unassigned(tmp_path):
    document = fitz.open()
    document.new_page(width=200, height=140)
    question = _question(1, [0, 0, 150, 120], [[20, 30, 90, 60], [20, 30, 90, 60]])
    # Give both distinct options identical source regions to model unresolved layout ownership.
    question["options"][1]["id"] = "2"
    sections = [{"section_name": "A", "questions": [question]}]

    result = attach_math_evidence(
        sections,
        [{"page": 1, "ordered_segments": [_math_page_token([35, 40, 48, 50])]}],
        document,
        tmp_path,
    )
    document.close()

    assert result["unassigned"] == 1
    assert all(not option["math_evidence"] for option in question["options"])
    assert not question["math_evidence"]


def test_unassigned_math_contains_explicit_reason_and_ownership_candidates(tmp_path):
    document = fitz.open()
    document.new_page(width=200, height=140)
    question = _question(1, [0, 0, 150, 120], [[20, 30, 60, 50], [54, 30, 94, 50]])
    sections = [{"section_name": "A", "questions": [question]}]
    page = {"page": 1, "ordered_segments": [_math_page_token([52, 35, 62, 45])]}

    result = attach_math_evidence(sections, [page], document, tmp_path)
    document.close()

    assert result["unassigned"] == 1
    fragment = result["unassigned_fragments"][0]
    assert fragment["reason"] == "overlaps_multiple_option_regions"
    assert fragment["atom_ids"] == ["atom-1", "atom-2"]
    assert {candidate["option_id"] for candidate in fragment["option_candidates"]} == {"1", "2"}
    assert fragment["page"] == 1 and len(fragment["bbox"]) == 4


def test_segmentation_validator_reports_duplicate_ids_and_region_overlaps():
    question = _question(1, [0, 0, 150, 120], [[20, 30, 70, 60], [40, 30, 90, 60]])
    question["options"][1]["id"] = "1"
    sections = [{"section_name": "A", "questions": [question, dict(question)]}]

    issues = validate_segmentation(sections)
    codes = {issue["code"] for issue in issues}
    assert "duplicate_question_id" in codes
    assert "duplicate_option_id" in codes
    assert "overlapping_option_regions" in codes


def test_uncertain_math_retains_source_crop_and_never_sets_latex(tmp_path):
    document = fitz.open()
    document.new_page(width=200, height=140)
    question = _question(1, [0, 0, 150, 120])
    sections = [{"section_name": "A", "questions": [question]}]

    result = attach_math_evidence(
        sections,
        [{"page": 1, "ordered_segments": [_math_page_token([20, 30, 40, 42], status="uncertain")]}],
        document,
        tmp_path,
    )
    document.close()

    evidence = question["math_evidence"][0]
    assert result["uncertain"] == 1
    assert evidence["latex"] is None
    assert evidence["review_required"] is True
    assert evidence["source_crop_filename"]
    assert (tmp_path / evidence["source_crop_filename"]).is_file()
    assert evidence["atom_ids"] == ["atom-1", "atom-2"]
    assert evidence["math_unit_ids"] == ["unit-1"]


def test_an_atom_cannot_be_assigned_to_two_questions(tmp_path):
    document = fitz.open()
    document.new_page(width=200, height=240)
    first = _question(1, [0, 0, 150, 100])
    second = _question(2, [0, 120, 150, 220])
    sections = [{"section_name": "A", "questions": [first, second]}]
    page = {
        "page": 1,
        "ordered_segments": [
            _math_page_token([20, 30, 40, 42], atom_ids=["shared-atom", "first-atom"]),
            _math_page_token([20, 150, 40, 162], atom_ids=["shared-atom", "second-atom"]),
        ],
    }

    result = attach_math_evidence(sections, [page], document, tmp_path)
    document.close()

    assert result["assigned"] == 1 and result["unassigned"] == 1
    unassigned = result["unassigned_fragments"][0]
    assert unassigned["reason"] == "atom_ids_already_owned"
    assert unassigned["conflicting_atom_owners"]["shared-atom"]["question_id"] == "q1"
