from app.services.engine import parse_questions
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
    assert questions[0]["options"] == [
        {"id": "1", "text": "3 m/s"}, {"id": "2", "text": "4 m/s"},
        {"id": "3", "text": "5 m/s"}, {"id": "4", "text": "6 m/s"},
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
    parsed = parse_questions(extracted["pages"])
    questions = [question for section in parsed for question in section["questions"]]
    assert len(questions) == 1
    assert questions[0]["question"]["en"] == "What is force?"
    assert "बल क्या है" in questions[0]["question"]["hi"]
    assert [option["id"] for option in questions[0]["options"]] == ["1", "2", "3", "4"]
