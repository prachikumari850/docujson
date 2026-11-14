
import re


ROMAN_NUMERAL_RE = re.compile(
    r"^(?=.)M{0,3}(CM|CD|D?C{0,3})"
    r"(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$",
    re.IGNORECASE,
)


def roman_to_int(value: str) -> int | None:
    numeral = value.strip().upper()

    if not ROMAN_NUMERAL_RE.fullmatch(numeral):
        return None

    values = {
        "I": 1, "V": 5, "X": 10,
        "L": 50, "C": 100, "D": 500, "M": 1000,
    }

    total = 0

    for index, character in enumerate(numeral):
        current = values[character]

        if index + 1 < len(numeral) and current < values[numeral[index + 1]]:
            total -= current
        else:
            total += current

    return total


def question_label_to_number(value: str) -> int | None:
    label = value.strip()

    if label.isdigit():
        number = int(label)
        return number if number > 0 else None

    return roman_to_int(label)
