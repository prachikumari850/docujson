import re
from typing import Any


QUESTION_PATTERN = re.compile(
    r"^\s*(?:(?:Q(?:uestion)?\.?\s*)?(\d{1,3})\s*[\).:]|"
    r"(\d{1,3})\s*[-:])\s*(.*?)\s*$",
    re.IGNORECASE,
)

OPTION_PATTERN = re.compile(
    r"^\s*[\(\[]?([A-Da-d])[\)\].:]?\s+(.+?)\s*$"
)

ANSWER_PATTERN = re.compile(
    r"^\s*(?:answer|ans\.?|उत्तर)\s*[:.-]\s*(.*?)\s*$",
    re.IGNORECASE,
)

SECTION_PATTERN = re.compile(
    r"^\s*(?:section|भाग|खंड)\s*([A-Z0-9IVX]+)?\s*[:.-]?\s*(.*?)\s*$",
    re.IGNORECASE,
)

MARKS_PATTERN = re.compile(
    r"\[\s*(\d+(?:\.\d+)?)\s*marks?\s*\]|"
    r"\(\s*(\d+(?:\.\d+)?)\s*marks?\s*\)|"
    r"\[\s*(\d+(?:\.\d+)?)\s*\]",
    re.IGNORECASE,
)


def is_hindi(text: str) -> bool:
    return bool(re.search(r"[\u0900-\u097F]", text))


def bilingual_text(text: str) -> dict[str, str | None]:
    text = text.strip()
    if not text:
        return {"en": None, "hi": None}

    hindi_chars = len(re.findall(r"[\u0900-\u097F]", text))
    latin_chars = len(re.findall(r"[A-Za-z]", text))

    if hindi_chars and latin_chars:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        english = [line for line in lines if not is_hindi(line)]
        hindi = [line for line in lines if is_hindi(line)]

        if english and hindi:
            return {
                "en": "\n".join(english),
                "hi": "\n".join(hindi),
            }

    if hindi_chars and not latin_chars:
        return {"en": None, "hi": text}

    return {"en": text, "hi": None}


def clean_question_text(text: str) -> tuple[str, float | None]:
    marks = None
    match = MARKS_PATTERN.search(text)

    if match:
        value = next((group for group in match.groups() if group), None)
        if value:
            marks = float(value)
        text = MARKS_PATTERN.sub("", text).strip()

    return text, marks


def detect_question_type(options: list[dict[str, str]]) -> str:
    return "mcq" if len(options) >= 2 else "subjective"


def parse_pages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current_section = {
        "section_name": "General",
        "questions": [],
    }

    current_question: dict[str, Any] | None = None
    question_counter = 0

    def flush_question() -> None:
        nonlocal current_question
        if current_question is None:
            return

        question_text = "\n".join(current_question.pop("_question_lines")).strip()
        question_text, marks = clean_question_text(question_text)

        current_question["question"] = bilingual_text(question_text)
        current_question["marks"] = (
            current_question.get("marks") if current_question.get("marks") is not None else marks
        )
        current_question["question_type"] = detect_question_type(
            current_question["options"]
        )

        if not question_text:
            current_question["review_required"] = True

        current_section["questions"].append(current_question)
        current_question = None

    def flush_section() -> None:
        flush_question()
        if current_section["questions"]:
            sections.append(current_section.copy())

    for page_data in pages:
        page_number = page_data["page"]
        lines = page_data["text"].splitlines()

        for raw_line in lines:
            line = raw_line.strip()
            if not line:
                continue

            section_match = SECTION_PATTERN.match(line)
            if section_match and (
                section_match.group(2)
                or line.upper().startswith(("SECTION", "भाग", "खंड"))
            ):
                flush_section()
                label = " ".join(
                    part for part in section_match.groups() if part
                ).strip()
                current_section = {
                    "section_name": label or line,
                    "questions": [],
                }
                continue

            answer_match = ANSWER_PATTERN.match(line)
            if answer_match and current_question:
                current_question["correct_answer"] = answer_match.group(1).strip()
                continue

            question_match = QUESTION_PATTERN.match(line)

            if question_match:
                flush_question()
                question_counter += 1

                number = question_match.group(1) or question_match.group(2)
                initial_text = question_match.group(3).strip()

                current_question = {
                    "question_id": f"q{question_counter}",
                    "question_number": number,
                    "question_type": "subjective",
                    "question": {"en": None, "hi": None},
                    "options": [],
                    "correct_answer": None,
                    "marks": None,
                    "source": {"page": page_number},
                    "media": [],
                    "review_required": False,
                    "_question_lines": [initial_text] if initial_text else [],
                }
                continue

            if current_question is None:
                if not current_section["questions"]:
                    current_section["section_name"] = line[:120]
                continue

            option_match = OPTION_PATTERN.match(line)
            if option_match:
                current_question["options"].append(
                    {
                        "id": option_match.group(1).upper(),
                        "text": option_match.group(2).strip(),
                    }
                )
                continue

            current_question["_question_lines"].append(line)

    flush_question()
    if current_section["questions"]:
        sections.append(current_section)

    return sections