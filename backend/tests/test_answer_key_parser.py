from app.services.answer_key import parse_answer_key


OFFICIAL_TEST_ANSWERS = [
    3, 4, 1, 2, 1, 1, 4, 1, 1, 2, 2, 2, 1, 2, 3, 1, 2, 4, 1, 1,
    1, 1, 1, 1, 3, 4, 2, 1, 3, 3, 4, 3, 3, 2, 1, 4, 3, 3, 3, 3,
    2, 3, 2, 2, 3, 3, 1, 4, 2, 1,
]


def test_official_answer_table_regression_fixture():
    pages = [
        {"page": 1, "text": "Q. " + " ".join(str(number) for number in range(1, 31)) + "\nA. " + " ".join(map(str, OFFICIAL_TEST_ANSWERS[:30]))},
        {"page": 2, "text": "Q. " + " ".join(str(number) for number in range(31, 51)) + "\nA. " + " ".join(map(str, OFFICIAL_TEST_ANSWERS[30:]))},
    ]
    parsed = parse_answer_key(pages)
    assert parsed["entry_count"] == 50
    assert parsed["answers"] == dict(enumerate(map(str, OFFICIAL_TEST_ANSWERS), start=1))
    assert not parsed["warnings"]


def test_individual_answer_formats():
    parsed = parse_answer_key([{"page": 1, "text": "1. C\nQ2 - B\n3) 2\nPage 7\nDate: 2026-11-09"}])
    assert parsed["answers"] == {1: "C", 2: "B", 3: "2"}


def test_conflicts_are_not_silently_matched():
    parsed = parse_answer_key([{"page": 1, "text": "1. C\n1) 2"}])
    assert 1 not in parsed["answers"]
    assert parsed["warnings"]


def test_duplicate_identical_answer_is_flagged_and_not_matched():
    parsed = parse_answer_key([{"page": 1, "text": "1. C\n1. C"}])
    assert 1 not in parsed["answers"]
    assert "duplicate" in parsed["warnings"][0]


def test_coordinate_rows_are_grouped_and_paired():
    q = [(10, 10, "Q."), (30, 10, "1"), (50, 10, "2"), (70, 10, "3")]
    a = [(10, 30, "A."), (30, 30, "4"), (50, 30, "2"), (70, 30, "1")]
    words = [(x, y, x + 5, y + 5, text, 0, 0, 0) for x, y, text in q + a]
    parsed = parse_answer_key([{"page": 1, "text": "", "words": words}])
    assert parsed["answers"] == {1: "4", 2: "2", 3: "1"}


def test_table_rows_can_continue_across_lines_and_pages():
    pages = [
        {"page": 1, "text": "Q. 1 2\n3 4\nA. 3 4"},
        {"page": 2, "text": "1 2"},
    ]
    parsed = parse_answer_key(pages)
    assert parsed["answers"] == {1: "3", 2: "4", 3: "1", 4: "2"}
