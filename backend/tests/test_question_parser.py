from app.services.engine import parse_questions, attach_media, _line_text_from_spans, _text_quality, repair_pdf_mojibake
import fitz
from app.services.engine import extract_pdf


def test_numbered_mcq_options_sections_and_spurious_page_numbers():
    pages = [
        {"page": 1, "text": "SECTION A\n1. Find the velocity.\n(1) 3 m/s\n(2) 4 m/s\n(3) 5 m/s\n(4) 6 m/s\n2. Solve the equation.\n(1) x=1\n(2) x=2\n(3) x=3\n(4) x=4\n7."},
        {"page": 2, "text": "SECTION B\n3. Select the vector.\n(1) i\n(2) j\n(3) k\n(4) zero"},
    ]
    sections = parse_questions(pages)
    assert [section["section_name"] for section in sections] == ["Section A", "Section B"]
    questions = [question for section in sections for question in section["questions"]]
    assert [question["question_number"] for question in questions] == [1, 2, 3]
    assert questions[0]["question_type"] == "mcq"
    assert [(option["id"], option["text"]) for option in questions[0]["options"]] == [
        ("1", "3 m/s"), ("2", "4 m/s"), ("3", "5 m/s"), ("4", "6 m/s"),
    ]
    assert "7." not in questions[1]["question"]["en"]


def test_pdf_two_column_order_and_bilingual_duplicate_merge(tmp_path):
    path = tmp_path / "two-columns.pdf"
    document = fitz.open()
    page = document.new_page(width=600, height=800)
    left = ["1. What is force?", "(1) one", "(2) two", "(3) three", "(4) four"]
    right = ["1. बल क्या है?", "(1) एक", "(2) दो", "(3) तीन", "(4) चार"]
    for index, line in enumerate(left):
        page.insert_text((40, 100 + index * 24), line, fontsize=12)
    for index, line in enumerate(right):
        page.insert_text((320, 100 + index * 24), line, fontsize=12, fontfile="C:/Windows/Fonts/Nirmala.ttc", fontname="Nirmala")
    document.save(path)
    document.close()

    extracted = extract_pdf(path, tmp_path / "media")
    assert extracted["pages"][0]["columns"] is not None
    assert extracted["pages"][0]["spans"]
    assert all({"text", "bbox", "font", "size", "flags"} <= set(span) for span in extracted["pages"][0]["spans"])
    parsed = parse_questions(extracted["pages"])
    questions = [question for section in parsed for question in section["questions"]]
    assert len(questions) == 1
    assert questions[0]["question"]["en"] == "What is force?"
    assert "बल क्या है" in questions[0]["question"]["hi"]
    assert [option["id"] for option in questions[0]["options"]] == ["1", "2", "3", "4"]


def test_adjacent_question_anchors_close_previous_question_region():
    lines = [f"{number}. Filler question {number}" for number in range(1, 19)]
    lines.extend(["19. Question nineteen body", "(1) option one", "20. Question twenty body", "(1) twenty one", "(2) twenty two", "(3) twenty three", "(4) twenty four"])
    lines.extend(f"{number}. Filler question {number}" for number in range(21, 27))
    lines.extend(["27. Question twenty seven body", "(1) twenty seven one", "28. Question twenty eight body", "(1) twenty eight one"])
    pages = [{
        "page": 1,
        "text": "SECTION A\n" + "\n".join(lines),
    }]
    questions = [q for section in parse_questions(pages) for q in section["questions"]]
    by_number = {q["question_number"]: q for q in questions}
    assert "Question twenty body" not in by_number[19]["question"]["en"]
    assert "twenty one" not in by_number[19]["options"][0]["text"]
    assert "Question twenty eight body" not in by_number[27]["question"]["en"]
    assert "twenty eight one" not in by_number[27]["options"][0]["text"]


def test_incomplete_options_are_flagged_with_reason():
    pages = [{"page": 1, "text": "1. Find x.\n(1)\n(2) two"}]
    question = parse_questions(pages)[0]["questions"][0]
    assert question["review_required"] is True
    assert any("Expected four choices" in reason for reason in question["review_reasons"])
    assert any("neither readable text nor associated media" in reason for reason in question["review_reasons"])


def test_preserves_math_symbols_superscripts_and_hindi():
    pages = [{"page": 1, "text": "\n".join([
        "1. \u0935\u0947\u0917 v\u00b2 = \u221a2 m/s \u0939\u0948?",
        "(1) \u222bx dx", "(2) 3 m/s\u00b2", "(3) \u03b8 + \u03c0", "(4) \u2192a",
    ])}]
    question = parse_questions(pages)[0]["questions"][0]
    combined_question = (question["question"]["en"] or "") + (question["question"]["hi"] or "")
    assert "v\u00b2" in combined_question
    assert "व" in question["question"]["hi"]
    assert "∫x dx" in question["options"][0]["text"]
    assert "m/s²" in question["options"][1]["text"]


def test_span_join_preserves_unicode_and_superscript_spacing():
    spans = [
        {"text": "α + ", "bbox": [10, 10, 31, 20], "size": 12},
        {"text": "v²", "bbox": [33, 8, 45, 20], "size": 12},
        {"text": "है", "bbox": [48, 10, 59, 20], "size": 12},
    ]
    assert _line_text_from_spans(spans) == "α + v² है"
    assert _text_quality("∫ α² + √x = 3") > 0.4


def test_recovers_recognizable_utf8_windows1252_pdf_text():
    assert repair_pdf_mojibake("à¤¯à¤¦à¤¿") == "यदि"
    assert repair_pdf_mojibake("cosâˆ’1, Î¸, Aâ†’") == "cos−1, θ, A→"
    assert repair_pdf_mojibake("ordinary text") == "ordinary text"


def test_blank_graph_option_gets_a_tightly_cropped_source_asset(tmp_path):
    source = tmp_path / "option-graph.pdf"
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    document = fitz.open()
    page = document.new_page(width=600, height=400)
    page.insert_text((40, 90), "1. Choose the graph")
    page.insert_text((60, 150), "(1)")
    page.draw_line((100, 170), (155, 135), color=(0, 0, 0), width=2)
    page.insert_text((180, 150), "(2) horizontal")
    page.insert_text((60, 185), "(3) rising")
    page.insert_text((180, 185), "(4) falling")
    document.save(source)
    document.close()

    from app.services.engine import extract_pdf
    extracted = extract_pdf(source, media_dir)
    sections = parse_questions(extracted["pages"])
    with fitz.open(source) as source_document:
        attach_media(sections, extracted["media"], extracted["pages"], source_document, media_dir)
    question = sections[0]["questions"][0]
    option = next(item for item in question["options"] if item["id"] == "1")
    assert option["text"] == ""
    assert option["media"]
    crop = fitz.Rect(option["media"][0]["bbox"])
    assert crop.width < 300 and crop.height < 100
