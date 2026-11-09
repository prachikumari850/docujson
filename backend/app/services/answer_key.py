import re
from collections import defaultdict
from typing import Any


INDIVIDUAL_ANSWER = re.compile(
    r"^\s*(?:Q(?:UESTION)?\s*)?(\d{1,3})\s*[).:-]\s*([1-4A-D])\s*$",
    re.IGNORECASE,
)
TABLE_QUESTION_ROW = re.compile(r"^\s*(?:Q\.?|QUESTION)\s*:?[\s-]*(.*)$", re.IGNORECASE)
TABLE_ANSWER_ROW = re.compile(r"^\s*(?:A\.?|ANS(?:WER)?)\s*:?[\s-]*(.*)$", re.IGNORECASE)
NUMBER = re.compile(r"\d{1,3}")
ANSWER = re.compile(r"[1-4]|[A-D]", re.IGNORECASE)


def _group_word_rows(words: list[tuple]) -> list[str]:
    grouped: list[list[tuple[float, tuple]]] = []
    for word in sorted(words, key=lambda item: (item[1], item[0])):
        y = float(word[1])
        for row in reversed(grouped[-3:]):
            if abs(row[0][0] - y) <= 3.5:
                row.append((y, word))
                break
        else:
            grouped.append([(y, word)])
    return [" ".join(str(item[1][4]) for item in sorted(row, key=lambda pair: pair[1][0])) for row in grouped]


def parse_answer_key(pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Extract indexed answers from line text and coordinate-grouped PDF words."""
    candidates: dict[int, list[str]] = defaultdict(list)
    pending_questions: list[int] = []
    awaiting_table_answers = False
    warnings: list[str] = []

    for page in pages:
        words = page.get("words") or []
        lines = _group_word_rows(words) if words else list(page.get("text", "").splitlines())

        for raw_line in lines:
            line = re.sub(r"\s+", " ", raw_line).strip()
            if not line:
                continue

            question_row = TABLE_QUESTION_ROW.match(line)
            if question_row:
                values = [int(value) for value in NUMBER.findall(question_row.group(1))]
                if len(values) >= 2:
                    pending_questions.extend(values)
                    awaiting_table_answers = False
                    continue

            answer_row = TABLE_ANSWER_ROW.match(line)
            if answer_row and pending_questions:
                awaiting_table_answers = True
                values = [value.upper() for value in ANSWER.findall(answer_row.group(1))]
                count = min(len(values), len(pending_questions))
                for question_number, answer in zip(pending_questions[:count], values[:count]):
                    candidates[question_number].append(answer)
                pending_questions = pending_questions[count:]
                if values:
                    continue

            if pending_questions and re.fullmatch(r"[\s\d,;|]+", line):
                continued_numbers = [int(value) for value in NUMBER.findall(line)]
                if not awaiting_table_answers and len(continued_numbers) >= 2 and continued_numbers[0] == pending_questions[-1] + 1 and all(right == left + 1 for left, right in zip(continued_numbers, continued_numbers[1:])) and continued_numbers[-1] <= 100:
                    pending_questions.extend(continued_numbers)
                    continue
                continued_answers = [value for value in re.findall(r"[1-4]", line)] if awaiting_table_answers else []
                if len(continued_answers) >= 2:
                    count = min(len(continued_answers), len(pending_questions))
                    for question_number, answer in zip(pending_questions[:count], continued_answers[:count]):
                        candidates[question_number].append(answer)
                    pending_questions = pending_questions[count:]
                    if not pending_questions:
                        awaiting_table_answers = False
                    continue

            individual = INDIVIDUAL_ANSWER.match(line)
            if individual:
                candidates[int(individual.group(1))].append(individual.group(2).upper())

    answers: dict[int, str] = {}
    for question_number, values in candidates.items():
        unique = list(dict.fromkeys(values))
        if len(values) == 1:
            answers[question_number] = unique[0]
        elif len(unique) == 1:
            warnings.append(f"Answer key contains duplicate entries for question {question_number}; review required.")
        else:
            warnings.append(f"Answer key has conflicting entries for question {question_number}; review required.")

    if pending_questions:
        warnings.append(f"Answer key table ended before answers were found for {len(pending_questions)} question numbers.")
    if not answers:
        warnings.append("No answer entries could be extracted from the answer key.")

    return {
        "answers": answers,
        "entry_count": sum(len(values) for values in candidates.values()),
        "warnings": warnings,
    }
