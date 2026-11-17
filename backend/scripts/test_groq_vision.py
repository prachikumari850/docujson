import re
import unicodedata
from difflib import SequenceMatcher
import base64
import json
import sys
from pathlib import Path

import fitz
import time
from groq import Groq , RateLimitError

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings


PDF_PATH = (
    BACKEND_DIR
    / "tests"
    / "fixtures"
    / "phase9"
    / "physics_question.pdf"
)

OUTPUT_PATH = (
    settings.storage_path
    / "groq_vision_test_pages_3_4.json"
)

PAGES_TO_TEST = [3, 4]
MAX_TOKENS = 900
RENDER_SCALE = 3
REGION_OVERLAP = 0.08
REGION_COUNT = 4
MAX_SPLIT_DEPTH = 3
MAX_RATE_LIMIT_RETRIES = 5
DEFAULT_RATE_LIMIT_WAIT = 25
MAX_AUTOMATIC_RATE_LIMIT_WAIT = 60

PROMPT = """
You are an expert examination-paper transcription system.

Transcribe all visible examination content in the supplied image region.

IMPORTANT RULES:
1. Transcribe printed text exactly. Do not solve questions.
2. Preserve original question numbers and sub-question numbering.
3. Extract every visible option and its original label.
4. Preserve equations, fractions, powers, subscripts, superscripts,
   Greek letters, mathematical symbols and units.
5. Preserve Hindi and English text in their original scripts.
6. Describe visible tables using their rows and columns.
7. Do not invent missing or unreadable content.
8. Mark uncertain text as [unclear].
9. Do not combine separate questions.
10. Describe relevant diagrams and figures.
11. Extract questions even if only part of the question is visible.
12. Do not assume that a question is complete if it continues
    outside the supplied image region.

QUESTION COMPLETENESS:
- Extract every question visible in this image region.
- Never stop after a fixed number of questions.
- Preserve the original question numbering.
- Include all visible parts of each question.
- Include partially visible questions and mark missing portions
  as uncertain.
- Do not omit a question because its text is difficult to read.

OPTION COMPLETENESS:
- Extract all visible options for every question.
- Preserve the original option labels.
- Do not assume there are only two or three options.
- If an option is partially visible, include its label and
  mark the unreadable portion as [unclear].
- Never silently omit a visible option.

OUTPUT VALIDATION:
- Every question must contain all these fields:
  question_number,
  question_text,
  options,
  equations,
  tables,
  diagram_description,
  uncertain_regions.
- Always return all fields, even when their values are empty.
- Preserve Hindi and English wherever both are visible.
- Do not translate, rewrite, or summarize original text.
- Return compact JSON without markdown.
- Do not include explanations outside the JSON.

Return valid JSON using this structure:

{
  "page_number": 3,
  "language": [],
  "questions": [
    {
      "question_number": "",
      "question_text": "",
      "options": [
        {
          "label": "",
          "text": ""
        }
      ],
      "equations": [],
      "tables": [],
      "diagram_description": "",
      "uncertain_regions": []
    }
  ],
  "other_visible_text": [],
  "page_level_uncertainties": []
}

If no questions are visible in this image region,
return an empty questions array.
"""

def get_page_regions(page):
    width = page.rect.width
    height = page.rect.height

    region_height = height / REGION_COUNT
    overlap = height * REGION_OVERLAP

    regions = []

    for index in range(REGION_COUNT):
        y_start = max(
            0,
            index * region_height - overlap,
        )

        y_end = min(
            height,
            (index + 1) * region_height + overlap,
        )

        regions.append(
            (
                f"region_{index + 1}",
                fitz.Rect(
                    0,
                    y_start,
                    width,
                    y_end,
                ),
            )
        )

    return regions


def get_region_image(page, clip):
    pix = page.get_pixmap(
        matrix=fitz.Matrix(RENDER_SCALE, RENDER_SCALE),
        clip=clip,
        colorspace=fitz.csRGB,
        alpha=False,
    )

    return base64.b64encode(
        pix.tobytes("jpeg")
    ).decode("utf-8")



def create_groq_completion(client, **kwargs):
    for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
        try:
            return client.chat.completions.create(**kwargs)

        except RateLimitError as exc:
            wait_seconds = DEFAULT_RATE_LIMIT_WAIT
            response = getattr(exc, "response", None)

            if response is not None:
                retry_after = response.headers.get("retry-after")

                if retry_after:
                    try:
                        wait_seconds = max(1, float(retry_after))
                    except (TypeError, ValueError):
                        pass

            match = re.search(
                r"try again in ([\d.]+)s",
                str(exc),
                re.IGNORECASE,
            )

            if match:
                wait_seconds = max(
                    wait_seconds,
                    float(match.group(1)),
                )

            if wait_seconds > MAX_AUTOMATIC_RATE_LIMIT_WAIT:
                raise RuntimeError(
                    f"Groq rate limit requires a wait of "
                    f"{wait_seconds:.1f} seconds "
                    f"({wait_seconds / 60:.1f} minutes). "
                    f"Automatic retry stopped because the "
                    f"maximum allowed wait is "
                    f"{MAX_AUTOMATIC_RATE_LIMIT_WAIT} seconds. "
                    f"Wait for the rate limit to reset and run again."
                ) from exc

            if attempt >= MAX_RATE_LIMIT_RETRIES:
                raise RuntimeError(
                    "Groq rate limit retries exhausted."
                ) from exc

            print(
                f"Groq rate limit reached. "
                f"Retrying in {wait_seconds:.1f} seconds "
                f"({attempt + 1}/{MAX_RATE_LIMIT_RETRIES})...",
                flush=True,
            )

            time.sleep(wait_seconds)

    raise RuntimeError("Groq retry attempts exhausted.")


def extract_region(
    client,
    page,
    page_number,
    region_name,
    clip,
    depth=0,
):
    print(
        f"Processing PDF page {page_number}, "
        f"{region_name} region..."
    )

    image_base64 = get_region_image(page, clip)

    response = create_groq_completion(
        client,
        model=settings.groq_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            PROMPT
                            + f"\n\nThis is the {region_name} "
                            f"region of PDF page {page_number}. "
                            f"Set page_number to {page_number}."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": (
                                "data:image/jpeg;base64,"
                                + image_base64
                            ),
                            "detail": "high",
                        },
                    },
                ],
            }
        ],
        temperature=0,
        max_tokens=MAX_TOKENS,
        response_format={"type": "json_object"},
    )

    choice = response.choices[0]

    if choice.finish_reason == "length":
        if depth >= MAX_SPLIT_DEPTH:
            raise ValueError(
                f"Groq output remains truncated on page "
                f"{page_number}, {region_name}, "
                f"after {depth} splits."
            )

        midpoint = (clip.y0 + clip.y1) / 2
        overlap = clip.height * REGION_OVERLAP

        subregions = [
            (
                f"{region_name}_top",
                fitz.Rect(
                    clip.x0,
                    clip.y0,
                    clip.x1,
                    min(clip.y1, midpoint + overlap),
                ),
            ),
            (
                f"{region_name}_bottom",
                fitz.Rect(
                    clip.x0,
                    max(clip.y0, midpoint - overlap),
                    clip.x1,
                    clip.y1,
                ),
            ),
        ]

        results = []

        for subregion_name, subregion_clip in subregions:
            results.append(
                extract_region(
                    client=client,
                    page=page,
                    page_number=page_number,
                    region_name=subregion_name,
                    clip=subregion_clip,
                    depth=depth + 1,
                )
            )

        return merge_region_results(results)

    content = choice.message.content

    if not content:
        raise ValueError(
            f"Groq returned an empty response for page "
            f"{page_number}, {region_name}."
        )

    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON on page {page_number}, "
            f"{region_name}: {exc}"
        ) from exc

    if not isinstance(result, dict):
        raise ValueError(
            f"Unexpected JSON structure on page "
            f"{page_number}, {region_name}."
        )

    if not isinstance(result.get("questions"), list):
        raise ValueError(
            f"Questions must be a list on page "
            f"{page_number}, {region_name}."
        )

    print(
        f"Page {page_number} ({region_name}): "
        f"{len(result['questions'])} questions returned"
    )

    return result


def normalize_comparison_text(value):
    if value is None:
        return ""

    value = unicodedata.normalize("NFKC", str(value))
    value = value.casefold()

    value = (
        value
        .replace("–", "-")
        .replace("—", "-")
        .replace("−", "-")
        .replace("﹣", "-")
    )

    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_list_item(value):
    normalized = normalize_comparison_text(value)

    if not normalized:
        return ""

    normalized = re.sub(r"\s+", "", normalized)

    return normalized


def merge_text(first, second):
    first = str(first or "").strip()
    second = str(second or "").strip()

    if not first:
        return second

    if not second:
        return first

    first_normalized = normalize_comparison_text(first)
    second_normalized = normalize_comparison_text(second)

    if first_normalized == second_normalized:
        return first if len(first) >= len(second) else second

    first_lines = [
        line.strip()
        for line in first.splitlines()
        if line.strip()
    ]

    second_lines = [
        line.strip()
        for line in second.splitlines()
        if line.strip()
    ]

    merged = []
    seen = set()

    for line in first_lines + second_lines:
        key = normalize_comparison_text(line)

        if key and key not in seen:
            seen.add(key)
            merged.append(line)

    return "\n".join(merged)

def merge_unique_lists(first, second):
    merged = []
    seen = set()

    for item in (first or []) + (second or []):
        if isinstance(item, str):
            key = normalize_list_item(item)
        else:
            key = json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
            )

        if key and key not in seen:
            seen.add(key)
            merged.append(item)

    return merged


def normalize_question_number(value):
    number = str(value or "").strip()
    number = re.sub(r"[.\s]+$", "", number)

    return number


def normalize_option_label(value):
    label = str(value or "").strip()
    label = re.sub(r"\s+", "", label)

    return label.rstrip(".")


def merge_options(first, second):
    merged = []
    option_indexes = {}

    for option in (first or []) + (second or []):
        if not isinstance(option, dict):
            continue

        label = normalize_option_label(
            option.get("label", "")
        )

        text = str(option.get("text", "")).strip()

        key = (
            f"label:{label}"
            if label
            else f"text:{normalize_comparison_text(text)}"
        )

        if key in option_indexes:
            index = option_indexes[key]

            merged[index]["text"] = merge_text(
                merged[index]["text"],
                text,
            )
        else:
            option_indexes[key] = len(merged)

            merged.append({
                "label": label,
                "text": text,
            })

    return merged


def get_question_key(question):
    number = normalize_question_number(
        question.get("question_number", "")
    )

    if number:
        return f"number:{number}"

    question_text = normalize_comparison_text(
        question.get("question_text", "")
    )

    if question_text:
        return f"text:{question_text}"

    return None

def normalize_question(question):
    question_number = normalize_question_number(
        question.get("question_number", "")
    )

    options = question.get("options") or []
    equations = question.get("equations") or []
    tables = question.get("tables") or []
    uncertain_regions = question.get("uncertain_regions") or []

    return {
        "question_number": question_number,
        "question_text": str(
            question.get("question_text", "")
        ).strip(),
        "options": options if isinstance(options, list) else [],
        "equations": equations if isinstance(equations, list) else [],
        "tables": tables if isinstance(tables, list) else [],
        "diagram_description": str(
            question.get("diagram_description", "")
        ).strip(),
        "uncertain_regions": (
            uncertain_regions
            if isinstance(uncertain_regions, list)
            else []
        ),
    }


def merge_questions(region_results):
    merged_questions = []
    question_indexes = {}

    for result in region_results:
        for raw_question in result.get("questions", []):
            if not isinstance(raw_question, dict):
                continue

            question = normalize_question(raw_question)
            key = get_question_key(question)

            if key is None:
                merged_questions.append(question)
                continue

            if key not in question_indexes:
                question_indexes[key] = len(merged_questions)
                merged_questions.append(question)
                continue

            index = question_indexes[key]
            existing = merged_questions[index]

            existing["question_text"] = merge_text(
                existing["question_text"],
                question["question_text"],
            )

            existing["options"] = merge_options(
                existing["options"],
                question["options"],
            )

            existing["equations"] = merge_unique_lists(
                existing["equations"],
                question["equations"],
            )

            existing["tables"] = merge_unique_lists(
                existing["tables"],
                question["tables"],
            )

            existing["diagram_description"] = merge_text(
                existing["diagram_description"],
                question["diagram_description"],
            )

            existing["uncertain_regions"] = merge_unique_lists(
                existing["uncertain_regions"],
                question["uncertain_regions"],
            )

    return merged_questions


def merge_region_results(results):
    merged = {
        "page_number": None,
        "language": [],
        "questions": merge_questions(results),
        "other_visible_text": [],
        "page_level_uncertainties": [],
    }

    for result in results:
        merged["page_number"] = (
            result.get("page_number")
            or merged["page_number"]
        )

        merged["language"] = merge_unique_lists(
            merged["language"],
            result.get("language", []),
        )

        merged["other_visible_text"] = merge_unique_lists(
            merged["other_visible_text"],
            result.get("other_visible_text", []),
        )

        merged["page_level_uncertainties"] = merge_unique_lists(
            merged["page_level_uncertainties"],
            result.get("page_level_uncertainties", []),
        )

    return merged

def validate_page_result(page_result, page_number):
    if not isinstance(page_result, dict):
        raise ValueError(
            f"Invalid page result for page {page_number}."
        )

    page_result["page_number"] = page_number

    list_fields = [
        "language",
        "questions",
        "other_visible_text",
        "page_level_uncertainties",
    ]

    for field in list_fields:
        if not isinstance(page_result.get(field), list):
            raise ValueError(
                f"Invalid '{field}' field on page {page_number}."
            )

    required_question_fields = [
        "question_number",
        "question_text",
        "options",
        "equations",
        "tables",
        "diagram_description",
        "uncertain_regions",
    ]

    for index, question in enumerate(page_result["questions"]):
        if not isinstance(question, dict):
            raise ValueError(
                f"Invalid question at index {index} "
                f"on page {page_number}."
            )

        for field in required_question_fields:
            if field not in question:
                raise ValueError(
                    f"Missing '{field}' in question {index + 1} "
                    f"on page {page_number}."
                )

        if not isinstance(question["options"], list):
            raise ValueError(
                f"Invalid options in question {index + 1} "
                f"on page {page_number}."
            )

        for option in question["options"]:
            if not isinstance(option, dict):
                raise ValueError(
                    f"Invalid option in question {index + 1} "
                    f"on page {page_number}."
                )

            if "label" not in option or "text" not in option:
                raise ValueError(
                    f"Option is missing label or text in "
                    f"question {index + 1} on page {page_number}."
                )

        for field in [
            "equations",
            "tables",
            "uncertain_regions",
        ]:
            if not isinstance(question[field], list):
                raise ValueError(
                    f"Invalid '{field}' in question {index + 1} "
                    f"on page {page_number}."
                )

        if not isinstance(question["question_number"], str):
            raise ValueError(
                f"Invalid question number in question {index + 1} "
                f"on page {page_number}."
            )

        if not isinstance(question["question_text"], str):
            raise ValueError(
                f"Invalid question text in question {index + 1} "
                f"on page {page_number}."
            )

        if not isinstance(question["diagram_description"], str):
            raise ValueError(
                f"Invalid diagram description in question "
                f"{index + 1} on page {page_number}."
            )

    return page_result

def extract_page(client, document, page_number):
    page = document[page_number - 1]

    print(f"\nProcessing PDF page {page_number}...")

    region_results = []

    for region_name, clip in get_page_regions(page):
        result = extract_region(
            client=client,
            page=page,
            page_number=page_number,
            region_name=region_name,
            clip=clip,
        )

        region_results.append(result)

    page_result = merge_region_results(region_results)
    page_result = validate_page_result(
        page_result,
        page_number,
    )

    print(
        f"Page {page_number}: "
        f"{len(page_result['questions'])} unique questions after merging"
    )

    return page_result


def main():
    if not settings.groq_api_key:
        raise RuntimeError(
            "GROQ_API_KEY is missing from backend/.env"
        )

    if not PDF_PATH.exists():
        raise FileNotFoundError(
            f"Question paper not found: {PDF_PATH}"
        )

    client = Groq(
        api_key=settings.groq_api_key,
        timeout=settings.groq_timeout_seconds,
        max_retries=0,
    )

    document = fitz.open(PDF_PATH)

    try:
        if max(PAGES_TO_TEST) > len(document):
            raise ValueError(
                f"PDF has only {len(document)} pages"
            )

        results = []

        for page_number in PAGES_TO_TEST:
            result = extract_page(
                client,
                document,
                page_number,
            )

            results.append(result)

        output = {
            "source_pdf": PDF_PATH.name,
            "model": settings.groq_model,
            "pages_tested": PAGES_TO_TEST,
            "results": results,
        }

        OUTPUT_PATH.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        OUTPUT_PATH.write_text(
            json.dumps(
                output,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print("\nGroq vision test completed successfully!")
        print(f"Output saved to:\n{OUTPUT_PATH}")

    finally:
        document.close()


if __name__ == "__main__":
    main()
