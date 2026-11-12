from app.services.engine import parse_questions, attach_media, _line_text_from_spans, _ordered_layout_lines, _cluster_drawing_rectangles, _spatial_reflow_fragments, _text_quality, repair_pdf_mojibake, _reconstruct_stacked_fractions, _has_encoding_artifacts, _has_suspicious_math_layout, _SUPERSCRIPTS, _SUBSCRIPTS, _associate_detached_vector_marks, numbered_options, bilingual
import fitz
from app.services.engine import extract_pdf


def test_bilingual_fields_retain_shared_math_only_source_lines():
    result = bilingual("π/4\n∫\nFind the value of x dx\nका मान x dx")
    assert "π/4" in result["en"] and "∫" in result["en"]
    assert "π/4" in result["hi"] and "∫" in result["hi"]
    assert "का मान" in result["hi"]


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
    assert {region["column"] for region in questions[0]["source"]["regions"]} == {"left", "right"}


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
    pages = [{"page": 1, "text": "SECTION A\n1. Complete.\n(1) one\n(2) two\n(3) three\n(4) four\n2. Find x.\n(1)\n(2) two"}]
    question = parse_questions(pages)[0]["questions"][1]
    assert question["review_required"] is True
    assert any("section's recurring pattern" in reason for reason in question["review_reasons"])
    assert any("neither readable text nor associated media" in reason for reason in question["review_reasons"])


def test_three_option_mcq_is_not_flagged_without_section_evidence():
    question = parse_questions([{"page": 1, "text": "1. Choose one.\nA. alpha\nB. beta\nC. gamma"}])[0]["questions"][0]
    assert question["question_type"] == "mcq"
    assert not any("fewer option labels" in reason for reason in question["review_reasons"])


def test_question_numbering_is_not_hard_capped_at_fifty():
    text = "\n".join(f"{number}. Item {number}." for number in range(1, 53))
    questions = [question for section in parse_questions([{"page": 1, "text": text}]) for question in section["questions"]]
    assert [question["question_number"] for question in questions] == list(range(1, 53))


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


def test_mojibake_is_flagged_without_rewriting_source_text():
    assert _has_encoding_artifacts("aâƒ— + bâƒ—")
    assert _has_encoding_artifacts("tÂ²")
    assert not _has_encoding_artifacts("Hindi English x² + α")


def test_script_maps_emit_real_unicode_and_repair_multiple_verified_encoding_layers():
    assert "2".translate(_SUPERSCRIPTS) == "\u00b2"
    assert "2".translate(_SUBSCRIPTS) == "\u2082"
    assert repair_pdf_mojibake("\u00c3\u00a0\u00c2\u00a4\u00c2\u00af") == "\u092f"


def test_fragmented_unit_vector_components_are_reviewed_for_visual_recovery():
    assert _has_suspicious_math_layout("1/√2 î + 1/2\nk̂")
    assert _has_suspicious_math_layout("1/√2 1/2 √3/2 k̂")
    assert _has_suspicious_math_layout("î + ĵ +\nî + ĵ + 1/2 k̂")
    assert not _has_suspicious_math_layout("î + 2ĵ − 3k̂")


def test_stacked_fraction_requires_actual_fraction_bar():
    numerator = (10.0, 20.0, "1", fitz.Rect(20, 20, 25, 30), [])
    denominator = (20.0, 20.0, "t", fitz.Rect(20, 40, 25, 50), [])
    unrelated = _reconstruct_stacked_fractions([numerator, denominator])
    assert [line[2] for line in unrelated] == ["1", "t"]

    with_bar = _reconstruct_stacked_fractions([numerator, denominator], [[19.5, 34, 25.5, 34.5]])
    assert len(with_bar) == 1
    assert with_bar[0][2] == "1/t"


def test_fraction_reconstruction_does_not_skip_intervening_content():
    numerator = (10.0, 20.0, "1", fitz.Rect(20, 20, 25, 30), [])
    unrelated = (18.0, 21.0, "x", fitz.Rect(21, 31, 24, 34), [])
    denominator = (20.0, 20.0, "t", fitz.Rect(20, 40, 25, 50), [])
    lines = _reconstruct_stacked_fractions(
        [numerator, unrelated, denominator],
        [[19.5, 34, 25.5, 34.5]],
    )
    assert [line[2] for line in lines] == ["1", "x", "t"]


def test_fraction_reconstruction_accepts_superscript_numerator_tokens():
    numerator = (10.0, 20.0, "t³", fitz.Rect(20, 20, 30, 30), [])
    denominator = (20.0, 20.0, "3", fitz.Rect(20, 40, 25, 50), [])
    lines = _reconstruct_stacked_fractions([numerator, denominator], [[19.5, 34, 30.5, 34.5]])
    assert [line[2] for line in lines] == ["t³/3"]


def test_fraction_reconstruction_keeps_radical_denominators_as_one_expression():
    numerator = (10.0, 20.0, "1", fitz.Rect(20, 20, 25, 30), [])
    denominator = (20.0, 20.0, "√2", fitz.Rect(19, 40, 28, 50), [])
    lines = _reconstruct_stacked_fractions([numerator, denominator], [[19.5, 34, 28, 34.5]])
    assert len(lines) == 1
    assert lines[0][2] == "1/√2"


def test_full_width_separator_preserves_column_reading_order():
    def line(y, x0, x1, value):
        rect = fitz.Rect(x0, y, x1, y + 10)
        return (rect.y0, rect.x0, value, rect, [])

    lines = [
        line(25, 20, 580, "Paper heading"),
        line(100, 35, 230, "Q1 left"),
        line(125, 35, 230, "Q1 continuation"),
        line(105, 330, 530, "Q2 right"),
        line(140, 330, 530, "Q2 continuation"),
        line(180, 20, 580, "Section B"),
        line(220, 35, 230, "Q3 left"),
        line(225, 330, 530, "Q4 right"),
    ]
    ordered, bounds = _ordered_layout_lines(lines, 600)
    assert [line[2] for line in ordered] == [
        "Paper heading", "Q1 left", "Q1 continuation", "Q2 right",
        "Q2 continuation", "Section B", "Q3 left", "Q4 right",
    ]
    assert bounds["left"][1] < bounds["right"][0]


def test_inline_math_fragments_follow_prose_by_shared_baseline_and_x_position():
    def fragment(y0, x0, text, baseline):
        rect = fitz.Rect(x0, y0, x0 + 24, y0 + 16)
        span = {"text": text, "bbox": list(rect), "size": 12, "origin": [x0, baseline], "chars": []}
        return (rect.y0, rect.x0, text, rect, [span])

    lines = [
        fragment(20.0, 35.0, "A =", 34.0),
        fragment(19.5, 5.0, "If", 34.0),
        fragment(19.8, 65.0, "B +", 34.0),
        fragment(20.2, 95.0, "C", 34.0),
        fragment(42.0, 5.0, "next line", 56.0),
    ]
    ordered, _ = _ordered_layout_lines(lines, 600)
    assert [line[2] for line in ordered] == ["If", "A =", "B +", "C", "next line"]


def test_inline_vector_variables_are_inserted_into_their_source_sentence():
    def char(value, x0, x1):
        return {"c": value, "bbox": [x0, 20, x1, 30], "origin": [x0, 30]}

    phrase = "between and is:-"
    phrase_chars = [
        char("b", 0, 5), char("e", 5, 10), char("t", 10, 15), char("w", 15, 20),
        char("e", 20, 25), char("e", 25, 30), char("n", 30, 35), char(" ", 35, 40),
        char("a", 45, 50), char("n", 50, 55), char("d", 55, 60), char(" ", 60, 65),
        char("i", 70, 75), char("s", 75, 80), char(":", 80, 85), char("-", 85, 90),
    ]

    def span(text, bbox, chars):
        return {"text": text, "bbox": list(bbox), "size": 12, "origin": [bbox[0], 30], "chars": chars}

    sentence_rect = fitz.Rect(0, 20, 100, 30)
    sentence = (20, 0, phrase, sentence_rect, [span(phrase, sentence_rect, phrase_chars)])
    a_rect = fitz.Rect(39, 20, 42, 30)
    c_rect = fitz.Rect(65, 20, 67, 30)
    a = (20, 39, "A", a_rect, [span("A", a_rect, [char("A", 39, 42)])])
    c = (20, 65, "C", c_rect, [span("C", c_rect, [char("C", 65, 67)])])

    ordered, _ = _ordered_layout_lines([sentence, a, c], 600)
    assert len(ordered) == 1
    assert ordered[0][2] == "between A and C is:-"


def test_vector_arrow_requires_above_base_geometry_not_arrow_text_alone():
    def span(text, bbox, char):
        return {
            "text": text, "bbox": bbox, "size": 12,
            "chars": [{"c": char, "bbox": bbox, "origin": [bbox[0], bbox[3]]}],
        }

    vector = _line_text_from_spans([
        span("A", [10, 10, 18, 20], "A"),
        span("→", [11, 4, 17, 8], "→"),
    ])
    relation = _line_text_from_spans([
        span("A", [10, 10, 18, 20], "A"),
        span(" → ", [21, 10, 31, 20], "→"),
        span("B", [34, 10, 42, 20], "B"),
    ])
    assert vector == "A\u20d7"
    assert "→" in relation
    assert "⃗" not in relation


def test_detached_vector_marks_attach_only_to_overlapping_base_characters():
    def base_line(text, bbox):
        chars = []
        x = bbox[0]
        for char in text:
            width = 5 if char != " " else 3
            chars.append({"c": char, "bbox": [x, bbox[1], x + width, bbox[3]], "origin": [x, bbox[3]]})
            x += width + 1
        span = {"text": text, "bbox": bbox, "size": 12, "chars": chars}
        return (bbox[1], bbox[0], text, fitz.Rect(bbox), [span])

    def mark_line(mark, bbox):
        char = {"c": mark, "bbox": bbox, "origin": [bbox[0], bbox[3]]}
        span = {"text": mark, "bbox": bbox, "size": 8, "chars": [char]}
        return (bbox[1], bbox[0], mark, fitz.Rect(bbox), [span])

    lines = [
        base_line("a + b", [20, 20, 53, 32]),
        mark_line("→", [20, 12, 30, 22]),
        base_line("i + j + k", [100, 60, 155, 72]),
        mark_line("ˆ", [100, 52, 106, 61]),
        mark_line("ˆ", [120, 52, 126, 61]),
        mark_line("ˆ", [140, 52, 146, 61]),
        base_line("A → B", [220, 100, 265, 112]),
    ]
    associated, evidence = _associate_detached_vector_marks(lines)
    values = [line[2] for line in associated]
    assert "a⃗ + b" in values
    assert "î + ĵ + k̂" in values
    assert "A → B" in values
    assert len(evidence) == 4


def test_superscript_source_option_labels_still_open_options():
    parsed = numbered_options("⁽¹⁾ always lies in plane containing a⃗ + b⃗")
    assert parsed[0]["id"] == "1"
    assert parsed[0]["text"] == "always lies in plane containing a⃗ + b⃗"


def test_single_character_superscripts_and_subscripts_use_line_baseline():
    def span(text, bbox, origin, size):
        return {
            "text": text, "bbox": bbox, "size": size,
            "chars": [{"c": text, "bbox": bbox, "origin": origin}],
        }

    superscript = _line_text_from_spans([
        span("x", [10, 10, 18, 20], [10, 20], 12),
        span("2", [18, 4, 22, 10], [18, 10], 7),
    ])
    subscript = _line_text_from_spans([
        span("a", [10, 10, 18, 20], [10, 20], 12),
        span("2", [18, 19, 22, 25], [18, 25], 7),
    ])
    assert superscript == "x²"
    assert subscript == "a₂"


def test_math_parts_are_sorted_horizontally_within_a_shared_formula_row():
    fragments = [
        {"text": "1/t", "bbox": [510, 448, 520, 459]},
        {"text": "t³/3", "bbox": [467, 447, 478, 458]},
        {"text": "− eᵗ +", "bbox": [480, 451, 500, 464]},
    ]
    assert _spatial_reflow_fragments(fragments) == "t³/3 − eᵗ + 1/t"


def test_vector_drawing_primitives_are_grouped_before_small_shape_filtering():
    drawings = [
        {"rect": [100, 100, 102, 170]},
        {"rect": [100, 168, 180, 170]},
        {"rect": [178, 100, 180, 170]},
        {"rect": [100, 100, 180, 102]},
    ]
    regions = _cluster_drawing_rectangles(drawings, fitz.Rect(0, 0, 600, 800))
    assert len(regions) == 1
    assert regions[0] == fitz.Rect(100, 100, 180, 170)


def test_media_association_respects_column_question_regions():
    pages = [{
        "page": 1, "width": 600, "height": 800,
        "lines": [
            (100, 40, "1. Left question", fitz.Rect(40, 100, 150, 112), []),
            (100, 330, "2. Right question", fitz.Rect(330, 100, 470, 112), []),
            (300, 40, "3. Next left", fitz.Rect(40, 300, 150, 312), []),
            (300, 330, "4. Next right", fitz.Rect(330, 300, 470, 312), []),
        ],
    }]

    def question(number, column, bbox):
        return {
            "question_id": f"q{number}", "question_number": number,
            "question": {"en": f"Question {number}", "hi": None},
            "source": {"page": 1, "bbox": bbox, "regions": [{"page": 1, "bbox": bbox, "column": column}]},
            "media": [], "options": [], "review_required": False, "review_reasons": [],
        }

    left = question(1, "left", [40, 100, 150, 112])
    right = question(2, "right", [330, 100, 470, 112])
    assets = [
        {"asset_id": "left-figure", "filename": "left.png", "type": "image", "source_page": 1, "bbox": [70, 130, 160, 200]},
        {"asset_id": "right-figure", "filename": "right.png", "type": "image", "source_page": 1, "bbox": [350, 130, 440, 200]},
    ]
    attach_media([{"section_name": "A", "questions": [left, right]}], assets, pages)
    assert [item["asset_id"] for item in left["media"]] == ["left-figure"]
    assert [item["asset_id"] for item in right["media"]] == ["right-figure"]


def test_formula_fragment_before_next_option_label_belongs_to_next_option():
    lines = [
        (100, 40, "Section A", fitz.Rect(40, 100, 120, 112), []),
        (130, 40, "1. Choose the expression", fitz.Rect(40, 130, 190, 142), []),
        (160, 60, "(1) 2/3 x", fitz.Rect(60, 160, 145, 172), []),
        (190, 98, "x2/2", fitz.Rect(98, 190, 120, 198), []),
        (195, 60, "(2) - 2x", fitz.Rect(60, 195, 130, 207), []),
        (225, 60, "(3) 3", fitz.Rect(60, 225, 90, 237), []),
        (255, 60, "(4) 4", fitz.Rect(60, 255, 90, 267), []),
    ]
    sections = parse_questions([{"page": 1, "width": 600, "height": 800, "text": "", "lines": lines}])
    options = sections[0]["questions"][0]["options"]
    assert "x2/2" not in options[0]["text"]
    assert "x2/2" in options[1]["text"]


def test_horizontal_option_content_regions_are_split_at_the_next_label():
    lines = [
        (100, 40, "Section A", fitz.Rect(40, 100, 120, 112), []),
        (130, 40, "1. Select the expressions", fitz.Rect(40, 130, 210, 142), []),
        (160, 60, "(1) x + 1     (2) y + 2", fitz.Rect(60, 160, 250, 172), []),
        (190, 60, "(3) x - 1     (4) y - 2", fitz.Rect(60, 190, 250, 202), []),
    ]
    sections = parse_questions([{"page": 1, "width": 600, "height": 800, "text": "", "lines": lines}])
    options = sections[0]["questions"][0]["options"]
    first_boxes = [fitz.Rect(box) for box in options[0]["source"]["content_bboxes"]]
    second_boxes = [fitz.Rect(box) for box in options[1]["source"]["content_bboxes"]]
    assert first_boxes and second_boxes
    assert max(box.x1 for box in first_boxes) < max(box.x1 for box in second_boxes)
    assert min(box.x0 for box in second_boxes) > min(box.x0 for box in first_boxes)
    assert max(box.x1 for box in first_boxes) - min(box.x0 for box in first_boxes) < lines[2][3].width


def test_multi_vector_row_above_next_question_anchor_is_owned_by_that_question():
    lines = [
        (100, 40, "Section A", fitz.Rect(40, 100, 120, 112), []),
        (130, 40, "1. Previous vector question", fitz.Rect(40, 130, 220, 142), []),
        (160, 60, "(1) a⃗ + b⃗", fitz.Rect(60, 160, 130, 172), []),
        (180, 60, "(2) a⃗ − b⃗", fitz.Rect(60, 180, 130, 192), []),
        (200, 60, "(3) can be zero", fitz.Rect(60, 200, 140, 212), []),
        (220, 60, "(4) cannot be zero", fitz.Rect(60, 220, 150, 232), []),
        (267, 60, "(2î + 2ĵ − 2k̂), (5î + yĵ + k̂)", fitz.Rect(60, 267, 260, 282), []),
        (270, 40, "2. If these vectors are coplanar, find y", fitz.Rect(40, 270, 270, 284), []),
        (300, 60, "(1) 1", fitz.Rect(60, 300, 90, 312), []),
        (320, 60, "(2) 2", fitz.Rect(60, 320, 90, 332), []),
        (340, 60, "(3) 3", fitz.Rect(60, 340, 90, 352), []),
        (360, 60, "(4) 4", fitz.Rect(60, 360, 90, 372), []),
    ]
    sections = parse_questions([{"page": 1, "width": 600, "height": 800, "text": "", "lines": lines}])
    questions = {item["question_number"]: item for item in sections[0]["questions"]}
    assert "2î + 2ĵ − 2k̂" not in questions[1]["original_text"]
    assert "2î + 2ĵ − 2k̂" in questions[2]["original_text"]
    assert len(questions[1]["options"]) == 4
    assert len(questions[2]["options"]) == 4


def test_tall_vector_formula_overlapping_next_anchor_is_not_absorbed_by_prior_option():
    lines = [
        (100, 40, "Section A", fitz.Rect(40, 100, 120, 112), []),
        (130, 40, "1. Previous question", fitz.Rect(40, 130, 180, 142), []),
        (160, 60, "(1) first", fitz.Rect(60, 160, 110, 172), []),
        (180, 60, "(2) second", fitz.Rect(60, 180, 120, 192), []),
        (200, 60, "(3) third", fitz.Rect(60, 200, 110, 212), []),
        (220, 60, "(4) fourth", fitz.Rect(60, 220, 120, 232), []),
        # PDF vector glyph boxes are tall and can start above their baseline.
        # Here the next question number sits inside the vector row's bbox.
        (237, 60, "(A⃗ × B⃗)", fitz.Rect(60, 237, 150, 284), []),
        (248, 40, "2. If A and B are vectors, state their relation", fitz.Rect(40, 248, 280, 262), []),
        (280, 60, "(1) one", fitz.Rect(60, 280, 110, 292), []),
        (300, 60, "(2) two", fitz.Rect(60, 300, 110, 312), []),
        (320, 60, "(3) three", fitz.Rect(60, 320, 120, 332), []),
        (340, 60, "(4) four", fitz.Rect(60, 340, 120, 352), []),
    ]
    sections = parse_questions([{"page": 1, "width": 600, "height": 800, "text": "", "lines": lines}])
    questions = {item["question_number"]: item for item in sections[0]["questions"]}
    assert all("A⃗ × B⃗" not in option["text"] for option in questions[1]["options"])
    assert "A⃗ × B⃗" in questions[2]["original_text"]


def test_math_fragment_above_option_row_prefers_nearest_label_over_later_row():
    lines = [
        (100, 40, "Section A", fitz.Rect(40, 100, 120, 112), []),
        (120, 40, "1. Choose the matching expression", fitz.Rect(40, 120, 230, 132), []),
        # This is a detached middle part of option 2, placed just above its
        # label. A farther look-ahead would incorrectly route it to option 4.
        (147, 215, "−eᵗ +", fitz.Rect(215, 147, 240, 160), []),
        (150, 60, "(1) first", fitz.Rect(60, 150, 120, 162), []),
        (150, 180, "(2) second", fitz.Rect(180, 150, 250, 162), []),
        (180, 60, "(3) third", fitz.Rect(60, 180, 120, 192), []),
        (180, 180, "(4) fourth", fitz.Rect(180, 180, 250, 192), []),
    ]
    sections = parse_questions([{"page": 1, "width": 600, "height": 800, "text": "", "lines": lines}])
    options = {item["id"]: item["text"] for item in sections[0]["questions"][0]["options"]}
    assert "−eᵗ +" in options["2"]
    assert all("−eᵗ +" not in options[label] for label in ("1", "3", "4"))


def test_math_fragment_baseline_slightly_below_label_stays_with_same_option_row():
    # Tall glyph boxes can put a formula before its label in bbox reading order,
    # while its actual baseline is a couple of points below that label. A broad
    # forward-only look-ahead incorrectly gives it to the next option row.
    label_span = {"text": "(2)", "origin": [180, 150], "size": 12, "chars": []}
    formula_span = {"text": "−eᵗ+1/t", "origin": [215, 152.5], "size": 11, "chars": []}
    lines = [
        (100, 40, "Section A", fitz.Rect(40, 100, 120, 112), []),
        (120, 40, "1. Choose the matching expression", fitz.Rect(40, 120, 230, 132), []),
        (150, 60, "(1) first", fitz.Rect(60, 150, 120, 162), []),
        (147, 215, "−eᵗ+1/t", fitz.Rect(215, 147, 250, 176), [formula_span]),
        (150, 180, "(2)", fitz.Rect(180, 150, 195, 165), [label_span]),
        (180, 60, "(3) third", fitz.Rect(60, 180, 120, 192), []),
        (180, 180, "(4) fourth", fitz.Rect(180, 180, 250, 192), []),
        (220, 40, "2. Next question", fitz.Rect(40, 220, 180, 232), []),
        (250, 60, "(1) next", fitz.Rect(60, 250, 120, 262), []),
    ]
    sections = parse_questions([{"page": 1, "width": 600, "height": 800, "text": "", "lines": lines}])
    questions = {q["question_number"]: q for q in sections[0]["questions"]}
    first_options = {option["id"]: option["text"] for option in questions[1]["options"]}
    assert "−eᵗ+1/t" in first_options["2"]
    assert all("−eᵗ+1/t" not in first_options[label] for label in ("1", "3", "4"))
    assert all("−eᵗ+1/t" not in option["text"] for option in questions[2]["options"])


def test_integral_limit_above_next_question_anchor_is_not_appended_to_previous_option():
    lines = [
        (100, 40, "Section A", fitz.Rect(40, 100, 120, 112), []),
        (130, 40, "1. Integrate the expression", fitz.Rect(40, 130, 190, 142), []),
        (160, 60, "(1) x", fitz.Rect(60, 160, 90, 172), []),
        (180, 60, "(2) y", fitz.Rect(60, 180, 90, 192), []),
        (200, 60, "(3) z", fitz.Rect(60, 200, 90, 212), []),
        (220, 60, "(4) w", fitz.Rect(60, 220, 90, 232), []),
        (251, 68, "π/4", fitz.Rect(68, 251, 82, 264), []),
        (270, 40, "2. Find the definite integral", fitz.Rect(40, 270, 200, 282), []),
        (300, 60, "(1) 1", fitz.Rect(60, 300, 90, 312), []),
        (320, 60, "(2) 2", fitz.Rect(60, 320, 90, 332), []),
        (340, 60, "(3) 3", fitz.Rect(60, 340, 90, 352), []),
        (360, 60, "(4) 4", fitz.Rect(60, 360, 90, 372), []),
    ]
    sections = parse_questions([{"page": 1, "width": 600, "height": 800, "text": "", "lines": lines}])
    questions = {q["question_number"]: q for q in sections[0]["questions"]}
    assert "π/4" not in questions[1]["options"][3]["text"]
    assert "π/4" in questions[2]["original_text"]


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
