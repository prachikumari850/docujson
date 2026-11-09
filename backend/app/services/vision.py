"""Optional local visual transcription through Ollama's image-capable API."""

from __future__ import annotations

import base64
from pathlib import Path

import httpx


TRANSCRIPTION_PROMPT = (
    "Transcribe only the visible printed text exactly as shown. Preserve all "
    "symbols, fraction structure, superscripts, subscripts, vector arrows, "
    "option labels, and punctuation. Do not solve, correct, infer, or fill "
    "unreadable content. Mark uncertainty as [unclear]. Return only a literal transcription."
)


def verify_math_image(
    image_path: Path,
    *,
    base_url: str,
    model: str,
    timeout_seconds: float,
) -> dict:
    """Return an untrusted transcript candidate; never mutate extracted text."""
    image_data = base64.b64encode(image_path.read_bytes()).decode("ascii")
    payload = {
        "model": model,
        "prompt": TRANSCRIPTION_PROMPT,
        "images": [image_data],
        "stream": False,
        "options": {"temperature": 0},
    }
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(f"{base_url.rstrip('/')}/api/generate", json=payload)
        response.raise_for_status()
        body = response.json()
    candidate = body.get("response")
    if body.get("done") is not True or not isinstance(candidate, str) or not candidate.strip():
        raise ValueError("Ollama returned an incomplete or empty visual transcription.")
    return {
        "model": body.get("model", model),
        "candidate_transcription": candidate.strip(),
        "done": True,
        "trusted_as_extracted_text": False,
    }
