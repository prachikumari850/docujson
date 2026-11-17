
import pytest

from app.services.layout import detect_page_layout


def make_line(text, x0, y0, x1, y1):
    return (y0, x0, text, (x0, y0, x1, y1), [])


def test_detects_single_column_layout():
    lines = [
        make_line("Question 1", 40, 50, 250, 65),
        make_line("Question text", 40, 80, 260, 95),
        make_line("Question 2", 40, 120, 250, 135),
    ]

    result = detect_page_layout(lines, 600, 800)

    assert result["layout_type"] == "single_column"
    assert len(result["columns"]) == 1
    assert result["line_order"] == [0, 1, 2]


def test_detects_two_columns():
    lines = [
        make_line("Left question 1", 40, 50, 250, 65),
        make_line("Right question 1", 330, 50, 550, 65),
        make_line("Left question 2", 40, 90, 250, 105),
        make_line("Right question 2", 330, 90, 550, 105),
    ]

    result = detect_page_layout(lines, 600, 800)

    assert result["layout_type"] == "multi_column"
    assert len(result["columns"]) == 2
    assert result["line_order"] == [0, 2, 1, 3]


def test_detects_three_columns():
    lines = [
        make_line("Column one A", 30, 50, 170, 65),
        make_line("Column two A", 220, 50, 360, 65),
        make_line("Column three A", 410, 50, 550, 65),
        make_line("Column one B", 30, 90, 170, 105),
        make_line("Column two B", 220, 90, 360, 105),
        make_line("Column three B", 410, 90, 550, 105),
    ]

    result = detect_page_layout(lines, 600, 800)

    assert result["layout_type"] == "multi_column"
    assert len(result["columns"]) == 3
    assert result["line_order"] == [0, 3, 1, 4, 2, 5]


def test_detects_uneven_column_widths():
    lines = [
        make_line("Wide left column", 30, 50, 260, 65),
        make_line("Narrow right column", 340, 50, 520, 65),
        make_line("Wide left column continued", 30, 90, 260, 105),
        make_line("Narrow right continued", 340, 90, 520, 105),
    ]

    result = detect_page_layout(lines, 600, 800)

    assert len(result["columns"]) == 2
    left_width = result["columns"][0]["bbox"][2] - result["columns"][0]["bbox"][0]
    right_width = result["columns"][1]["bbox"][2] - result["columns"][1]["bbox"][0]

    assert left_width > right_width
    assert result["line_order"] == [0, 2, 1, 3]


def test_full_width_line_separates_column_bands():
    lines = [
        make_line("Left upper", 40, 50, 250, 65),
        make_line("Right upper", 330, 50, 550, 65),
        make_line("Full width heading", 40, 120, 560, 140),
        make_line("Left lower", 40, 170, 250, 185),
        make_line("Right lower", 330, 170, 550, 185),
    ]

    result = detect_page_layout(lines, 600, 800)

    spanning = [
        region for region in result["regions"]
        if region["region_type"] == "spanning"
    ]

    assert len(spanning) == 1
    assert spanning[0]["line_indices"] == [2]
    assert result["line_order"] == [0, 1, 2, 3, 4]


def test_preserves_all_source_line_indexes():
    lines = [
        make_line("Left A", 40, 50, 250, 65),
        make_line("Right A", 330, 50, 550, 65),
        make_line("Left B", 40, 90, 250, 105),
        make_line("Right B", 330, 90, 550, 105),
    ]

    result = detect_page_layout(lines, 600, 800)

    assert sorted(result["line_order"]) == [0, 1, 2, 3]
    assert len(result["line_order"]) == len(set(result["line_order"]))


def test_empty_page_returns_empty_layout():
    result = detect_page_layout([], 600, 800)

    assert result["layout_type"] == "empty"
    assert result["columns"] == []
    assert result["regions"] == []
    assert result["reading_order"] == []
    assert result["line_order"] == []


def test_invalid_page_dimensions_are_rejected():
    with pytest.raises(ValueError):
        detect_page_layout([], 0, 800)

    with pytest.raises(ValueError):
        detect_page_layout([], 600, -1)


def test_invalid_bounding_box_is_rejected():
    lines = [
        make_line("Invalid", 100, 50, 40, 65),
    ]

    with pytest.raises(ValueError):
        detect_page_layout(lines, 600, 800)


def test_regions_have_unique_ids_and_order():
    lines = [
        make_line("Left A", 40, 50, 250, 65),
        make_line("Right A", 330, 50, 550, 65),
        make_line("Full width", 40, 120, 560, 140),
        make_line("Left B", 40, 170, 250, 185),
        make_line("Right B", 330, 170, 550, 185),
    ]

    result = detect_page_layout(lines, 600, 800)

    region_ids = [
        region["region_id"] for region in result["regions"]
    ]

    assert len(region_ids) == len(set(region_ids))
    assert result["reading_order"] == region_ids

    for expected_order, region in enumerate(result["regions"], start=1):
        assert region["reading_order"] == expected_order


def test_detects_bilingual_columns_with_narrow_gutter():
    lines = [
        make_line("Hindi heading", 115, 83, 222, 101),
        make_line("English heading", 355, 83, 498, 101),
        make_line("Hindi question 1", 40, 109, 290, 127),
        make_line("English question 1", 305, 109, 555, 127),
        make_line("Hindi question 2", 40, 207, 290, 225),
        make_line("English question 2", 305, 207, 555, 225),
        make_line("Hindi question 3", 40, 325, 290, 343),
        make_line("English question 3", 305, 325, 555, 343),
    ]

    result = detect_page_layout(lines, 594.96, 841.92)

    assert result["layout_type"] == "multi_column"
    assert len(result["columns"]) == 2


def test_assigns_short_question_numbers_to_nearest_column():
    lines = [
        make_line("1.", 40, 50, 48, 65),
        make_line("Hindi question text", 68, 50, 290, 65),
        make_line("1.", 305, 50, 313, 65),
        make_line("English question text", 333, 50, 555, 65),
        make_line("2.", 40, 100, 48, 115),
        make_line("Hindi next question", 68, 100, 290, 115),
        make_line("2.", 305, 100, 313, 115),
        make_line("English next question", 333, 100, 555, 115),
    ]

    result = detect_page_layout(lines, 594.96, 841.92)

    assert len(result["columns"]) == 2

    assigned_indices = [
        index
        for column in result["columns"]
        for index in column["line_indices"]
    ]

    assert sorted(assigned_indices) == list(range(len(lines)))


def test_local_two_up_options_do_not_create_page_columns():
    lines = [
        make_line("Question prompt", 40, 50, 280, 65),
        make_line("Option A", 68, 80, 150, 95),
        make_line("Option B", 175, 80, 260, 95),
        make_line("Question 2 prompt", 40, 120, 280, 135),
        make_line("Option C", 68, 150, 150, 165),
        make_line("Option D", 175, 150, 260, 165),
    ]

    result = detect_page_layout(lines, 600, 800)

    assert result["layout_type"] == "single_column"
    assert len(result["columns"]) == 1


def test_full_width_heading_does_not_merge_bilingual_columns():
    lines = [
        make_line("Hindi upper", 40, 50, 290, 65),
        make_line("English upper", 305, 50, 555, 65),
        make_line("Full width section heading", 40, 120, 560, 140),
        make_line("Hindi lower", 40, 170, 290, 185),
        make_line("English lower", 305, 170, 555, 185),
    ]

    result = detect_page_layout(lines, 594.96, 841.92)

    assert result["layout_type"] == "multi_column"
    assert len(result["columns"]) == 2

    spanning = [
        region
        for region in result["regions"]
        if region["region_type"] == "spanning"
    ]

    assert len(spanning) == 1
    assert spanning[0]["line_indices"] == [2]


def test_repeated_two_up_options_do_not_create_page_columns():
    lines = [
        make_line("Question one prompt", 40, 40, 280, 55),
        make_line("Option A", 68, 70, 150, 85),
        make_line("Option B", 175, 70, 260, 85),
        make_line("Question two prompt", 40, 110, 280, 125),
        make_line("Option C", 68, 140, 150, 155),
        make_line("Option D", 175, 140, 260, 155),
        make_line("Question three prompt", 40, 180, 280, 195),
        make_line("Option E", 68, 210, 150, 225),
        make_line("Option F", 175, 210, 260, 225),
    ]

    result = detect_page_layout(lines, 600, 800)

    assert result["layout_type"] == "single_column"
    assert len(result["columns"]) == 1


def test_every_source_line_is_assigned_to_exactly_one_region():
    lines = [
        make_line("1.", 40, 50, 48, 65),
        make_line("Left question one", 68, 50, 290, 65),
        make_line("1.", 305, 50, 313, 65),
        make_line("Right question one", 333, 50, 555, 65),
        make_line("Full width heading", 40, 120, 560, 140),
        make_line("2.", 40, 170, 48, 185),
        make_line("Left question two", 68, 170, 290, 185),
        make_line("2.", 305, 170, 313, 185),
        make_line("Right question two", 333, 170, 555, 185),
    ]

    result = detect_page_layout(lines, 594.96, 841.92)

    region_line_indices = [
        index
        for region in result["regions"]
        for index in region["line_indices"]
    ]

    assert sorted(region_line_indices) == list(range(len(lines)))
    assert len(region_line_indices) == len(set(region_line_indices))
    assert len(result["line_order"]) == len(set(result["line_order"]))
    assert not result["warnings"]
