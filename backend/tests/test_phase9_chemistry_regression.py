"""Real-paper regression for lettered statement lists preceding MCQ choices.

The Chemistry source is a second subject and PDF layout from the Physics
baseline. Its (a)/(b) reaction steps and statement labels precede numbered
answer choices; those labels must remain in the question body.
"""
from __future__ import annotations

from pathlib import Path

import fitz

from app.services.engine import (
    _has_detached_vector_combining_mark,
    _line_text_from_spans,
    _ordered_layout_lines,
    classify_mcq_records,
    parse_questions,
)
from app.services.answer_key import parse_answer_key


FIXTURES = Path(__file__).parent / "fixtures" / "phase9"
CHEMISTRY_QP = FIXTURES / "srg_chemistry_qp.pdf"


def test_reaction_arrow_operator_is_not_misreported_as_a_detached_vector_accent():
    assert not _has_detached_vector_combining_mark("CH3Br + OH -> CH3OH + Br")
    assert not _has_detached_vector_combining_mark("a\u20d7 + b\u20d7")
    assert _has_detached_vector_combining_mark("\u20d7 + a")


def _page_data(page: fitz.Page, page_number: int) -> dict:
    lines = []
    for block in page.get_text("dict", sort=False).get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = _line_text_from_spans(spans).strip()
            if not text:
                continue
            bbox = fitz.Rect(line["bbox"])
            lines.append((bbox.y0, bbox.x0, text, bbox, spans))
    ordered, _ = _ordered_layout_lines(lines, page.rect.width)
    return {
        "page": page_number,
        "width": page.rect.width,
        "height": page.rect.height,
        "lines": ordered,
        "text": "\n".join(line[2] for line in ordered),
        "needs_review": False,
    }


def _prefix_through_question_28() -> dict:
    """Supply numbering context; tested source pages remain untouched."""
    lines = [(20.0, 40.0, "SECTION A", fitz.Rect(40, 20, 110, 32), [])]
    for number in range(1, 29):
        y = 40.0 + number * 18.0
        bbox = fitz.Rect(40, y, 62, y + 12)
        lines.append((y, 40.0, f"{number}.", bbox, []))
    return {
        "page": 1,
        "width": 595.0,
        "height": 842.0,
        "lines": lines,
        "text": "SECTION A\n" + "\n".join(f"{number}." for number in range(1, 29)),
        "needs_review": False,
    }


def test_real_chemistry_lettered_statements_remain_in_stem_and_numeric_choices_win():
    assert CHEMISTRY_QP.is_file(), f"Required real-paper fixture is missing: {CHEMISTRY_QP}"
    with fitz.open(CHEMISTRY_QP) as doc:
        pages = [
            _prefix_through_question_28(),
            _page_data(doc[10], 11),
            _page_data(doc[11], 12),
        ]

    parsed = parse_questions(pages)
    exported, summary = classify_mcq_records(parsed)
    records = {q["question_number"]: q for section in exported for q in section["questions"]}

    # Q29 reaction steps and Q30's lettered statements are part of each stem.
    assert "(a)" in records[29]["original_text"]
    assert "(b)" in records[29]["original_text"]
    assert "(a)" in records[30]["original_text"]
    assert "(h)" in records[30]["original_text"]
    assert "For above reaction" in (records[30]["question"]["en"] or "")
    assert [option["id"] for option in records[30]["options"]] == ["1", "2", "3", "4"]

    # Q33's figure is followed by lettered statements, then actual MCQ choices.
    assert records[33]["question"]["en"]
    assert "By increasing temperature" in (records[33]["question"]["en"] or "")
    assert [option["id"] for option in records[33]["options"]] == ["1", "2", "3", "4"]
    assert records[33]["classification_status"] == "confirmed_mcq"


def test_alpha_options_are_preserved_when_no_later_numeric_choice_run_exists():
    text_lines = [
        (20.0, 40.0, "SECTION A", fitz.Rect(40, 20, 110, 32), []),
        (50.0, 40.0, "1. Select the correct statement", fitz.Rect(40, 50, 220, 64), []),
        (90.0, 60.0, "(A) First choice", fitz.Rect(60, 90, 170, 104), []),
        (112.0, 60.0, "(B) Second choice", fitz.Rect(60, 112, 180, 126), []),
    ]
    page = {
        "page": 1,
        "width": 595.0,
        "height": 842.0,
        "lines": text_lines,
        "text": "\n".join(line[2] for line in text_lines),
        "needs_review": False,
    }
    sections = parse_questions([page])
    exported, _ = classify_mcq_records(sections)
    question = exported[0]["questions"][0]
    assert [option["id"] for option in question["options"]] == ["A", "B"]


def test_numeric_choices_in_following_question_do_not_relabel_alpha_choices():
    text_lines = [
        (20.0, 40.0, "SECTION A", fitz.Rect(40, 20, 110, 32), []),
        (50.0, 40.0, "1. Select the correct statement", fitz.Rect(40, 50, 220, 64), []),
        (80.0, 60.0, "(A) First choice", fitz.Rect(60, 80, 170, 94), []),
        (100.0, 60.0, "(B) Second choice", fitz.Rect(60, 100, 180, 114), []),
        (140.0, 40.0, "2. Select a number", fitz.Rect(40, 140, 170, 154), []),
        (170.0, 60.0, "(1) Numeric one", fitz.Rect(60, 170, 160, 184), []),
        (192.0, 60.0, "(2) Numeric two", fitz.Rect(60, 192, 160, 206), []),
    ]
    page = {
        "page": 1,
        "width": 595.0,
        "height": 842.0,
        "lines": text_lines,
        "text": "\n".join(line[2] for line in text_lines),
        "needs_review": False,
    }
    sections = parse_questions([page])
    records = {q["question_number"]: q for section in sections for q in section["questions"]}
    assert [option["id"] for option in records[1]["options"]] == ["A", "B"]
    assert [option["id"] for option in records[2]["options"]] == ["1", "2"]


def test_real_chemistry_answer_key_has_numbered_entries_one_through_fifty():
    answer_key = FIXTURES / "srg_chemistry_answer_key.pdf"
    assert answer_key.is_file(), f"Required real answer-key fixture is missing: {answer_key}"
    with fitz.open(answer_key) as doc:
        pages = [
            {"text": page.get_text(), "words": page.get_text("words")}
            for page in doc
        ]

    parsed = parse_answer_key(pages)
    assert parsed["entry_count"] == 50
    assert set(parsed["answers"]) == set(range(1, 51))
    assert not parsed["warnings"]
