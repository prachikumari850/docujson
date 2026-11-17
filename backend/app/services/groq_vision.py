
"""Groq Vision page-level transcription for DocuJSON."""

from __future__ import annotations

import base64
import json
import logging

import fitz
from groq import Groq

from app.config import settings

logger = logging.getLogger("docujson")


# Keep the detailed transcription rules from test_groq_vision.py.
PROMPT = """
Transcribe all visible printed content on this PDF page exactly.

Return valid JSON with this structure:

{
  "page_number": 1,
  "language": "English/Hindi/Bilingual",
  "questions": [
    {
      "question_number": "1",
      "question_text": {
        "en": "",
        "hi": ""
      },
      "options": [
        {
          "label": "1",
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

Rules:
- Preserve all question numbers and sub-question numbers.
- Preserve every option label and its text.
- Preserve English and Hindi exactly in their respective scripts.
- Preserve mathematical symbols, fractions, superscripts,
  subscripts, vector arrows and equations.
- Do not solve questions.
- Do not correct the original text.
- Do not invent missing information.
- Do not omit visible content.
- Describe diagrams without interpreting or solving them.
- Mark unreadable content as [unclear].
- Return JSON only.

"""


def get_page_image(
    source_document: fitz.Document,
    page_number: int,
) -> str:
    """Render a one-based PDF page number into a base64 JPEG."""

    if page_number < 1 or page_number > len(source_document):
        raise ValueError(f"Invalid PDF page number: {page_number}")

    page = source_document[page_number - 1]

    pixmap = page.get_pixmap(
        matrix=fitz.Matrix(3, 3),
        alpha=False,
    )

    image_bytes = pixmap.tobytes("jpeg")

    return base64.b64encode(image_bytes).decode("ascii")


def verify_page_with_groq(
    source_document: fitz.Document,
    page_number: int,
    client: Groq,
) -> dict:
    """Return an untrusted Groq visual transcription candidate."""

    image_base64 = get_page_image(
        source_document,
        page_number,
    )

    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            PROMPT
                            + f"\nTranscribe PDF page {page_number}."
                            + f"\nSet page_number to {page_number}."
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
        max_tokens=4000,
        response_format={"type": "json_object"},
    )

    message = response.choices[0].message
    content = message.content

    if not content:
        raise ValueError(
            f"Groq returned an empty response for page {page_number}."
        )

    result = json.loads(content)

    if not isinstance(result, dict):
        raise ValueError("Groq response must be a JSON object.")

    if not isinstance(result.get("questions"), list):
        raise ValueError(
            f"Groq returned an invalid questions list for page {page_number}."
        )

    if message.finish_reason == "length":
        raise ValueError(
            f"Groq response was truncated on page {page_number}."
        )

    return {
        "page_number": page_number,
        "model": settings.groq_model,
        "transcription": result,
        "trusted_as_extracted_text": False,
    }


def verify_pages_with_groq(
    source_document: fitz.Document,
    page_numbers: list[int],
) -> dict:
    """Verify selected PDF pages without modifying Python extraction."""

    summary = {
        "enabled": bool(settings.groq_enabled),
        "available": False,
        "used": False,
        "model": settings.groq_model if settings.groq_enabled else None,
        "pages_attempted": 0,
        "pages_completed": 0,
        "results": [],
        "warnings": [],
    }

    if not settings.groq_enabled:
        return summary

    if not settings.groq_api_key:
        summary["warnings"].append(
            "Groq is enabled but GROQ_API_KEY is missing."
        )
        return summary

    try:
        client = Groq(
            api_key=settings.groq_api_key,
            timeout=settings.groq_timeout_seconds,
            max_retries=2,
        )

        summary["available"] = True

    except Exception as error:
        summary["warnings"].append(
            f"Groq initialization failed: {type(error).__name__}: {error}"
        )
        return summary

    for page_number in sorted(set(page_numbers)):
        summary["pages_attempted"] += 1

        try:
            result = verify_page_with_groq(
                source_document,
                page_number,
                client,
            )

            summary["results"].append(result)
            summary["pages_completed"] += 1
            summary["used"] = True

        except Exception as error:
            logger.exception(
                "Groq verification failed for page %s",
                page_number,
            )

            summary["warnings"].append(
                f"Groq verification failed for page {page_number}: "
                f"{type(error).__name__}: {error}"
            )

    return summary
