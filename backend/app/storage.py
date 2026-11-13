import json
import re
from pathlib import Path
from threading import RLock
from uuid import uuid4
from copy import deepcopy
from datetime import datetime, timezone
from app.config import settings


LOCK = RLock()
CONVERSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")


def _validate_conversion_id(conversion_id: str) -> str:
    if (
        not isinstance(conversion_id, str)
        or not CONVERSION_ID_RE.fullmatch(conversion_id)
    ):
        raise FileNotFoundError("Conversion not found.")
    return conversion_id


def create_job(organization_id: str, created_by: str):
    if not organization_id or not created_by:
        raise ValueError("Organization and creator are required.")

    conversion_id = uuid4().hex
    root = settings.storage_path / conversion_id

    (root / "media").mkdir(parents=True, exist_ok=True)

    write_job(
        conversion_id,
        {
            "conversion_id": conversion_id,
            "organization_id": organization_id,
            "created_by": created_by,
            "status": "queued",
            "progress": 0,
            "stage": "Waiting to start",
            "error": None,
            "result": None,
            "review_decisions": {},
        },
    )

    return conversion_id, root


def job_dir(conversion_id: str) -> Path:
    conversion_id = _validate_conversion_id(conversion_id)
    path = settings.storage_path / conversion_id

    if not path.is_dir():
        raise FileNotFoundError("Conversion not found.")

    return path


def write_job(conversion_id: str, data: dict):
    conversion_id = _validate_conversion_id(conversion_id)
    root = settings.storage_path / conversion_id
    root.mkdir(parents=True, exist_ok=True)

    temporary = root / "status.tmp"
    destination = root / "status.json"

    with LOCK:
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(destination)


def read_job(conversion_id: str) -> dict:
    with LOCK:
        path = job_dir(conversion_id) / "status.json"

        if not path.is_file():
            raise FileNotFoundError("Conversion not found.")

        return json.loads(path.read_text(encoding="utf-8"))

def read_job_for_organization(
    conversion_id: str,
    organization_id: str,
) -> dict:
    if not organization_id:
        raise FileNotFoundError("Conversion not found.")

    data = read_job(conversion_id)

    if data.get("organization_id") != organization_id:
        raise FileNotFoundError("Conversion not found.")

    return data


def job_dir_for_organization(
    conversion_id: str,
    organization_id: str,
) -> Path:
    read_job_for_organization(conversion_id, organization_id)
    return job_dir(conversion_id)


def list_jobs(
    limit: int = 20,
    offset: int = 0,
    organization_id: str | None = None,
) -> tuple[list[dict], int]:
    storage_root = settings.storage_path
    jobs = []

    with LOCK:
        for directory in storage_root.iterdir():
            if (
                not directory.is_dir()
                or not CONVERSION_ID_RE.fullmatch(directory.name)
            ):
                continue

            status_path = directory / "status.json"

            if not status_path.is_file():
                continue

            try:
                data = json.loads(
                    status_path.read_text(encoding="utf-8")
                )
                modified_at = status_path.stat().st_mtime
            except (OSError, json.JSONDecodeError):
                continue

            if not isinstance(data, dict):
                continue

            if (
                organization_id is not None
                and data.get("organization_id") != organization_id
            ):
                continue

            data["_modified_at"] = modified_at
            jobs.append(data)

    jobs.sort(
        key=lambda job: job["_modified_at"],
        reverse=True,
    )

    total = len(jobs)
    page = jobs[offset:offset + limit]

    for job in page:
        job.pop("_modified_at", None)

    return page, total

def update_job(conversion_id: str, **values):
    with LOCK:
        data = read_job(conversion_id)
        data.update(values)
        write_job(conversion_id, data)
        return data


def save_review_decision(
    conversion_id: str,
    question_id: str,
    decision: str,
    note: str | None,
    reviewed_at: str,
):
    with LOCK:
        data = read_job(conversion_id)

        if data.get("status") != "completed":
            raise ValueError("Conversion is not completed.")

        result = data.get("result") or {}
        question_found = any(
            question.get("question_id") == question_id
            for section in result.get("sections") or []
            for question in section.get("questions") or []
        )

        if not question_found:
            raise KeyError("Question not found.")

        decisions = data.setdefault("review_decisions", {})
        decisions[question_id] = {
            "decision": decision,
            "note": note,
            "reviewed_at": reviewed_at,
        }

        write_job(conversion_id, data)

        return decisions[question_id]


def save_answer_key_decision(
    conversion_id: str,
    entry_id: str,
    decision: str,
    corrected_answer: str | None,
    note: str | None,
    reviewed_at: str,
):
    with LOCK:
        data = read_job(conversion_id)

        if data.get("status") != "completed":
            raise ValueError("Conversion is not completed.")

        answer_key = data.get("answer_key") or {}

        entry_found = any(
            entry.get("entry_id") == entry_id
            for entry in answer_key.get("entries") or []
        )

        if not entry_found:
            raise KeyError("Answer-key entry not found.")

        decisions = data.setdefault("answer_key_decisions", {})

        decisions[entry_id] = {
            "decision": decision,
            "corrected_answer": corrected_answer,
            "note": note,
            "reviewed_at": reviewed_at,
        }

        write_job(conversion_id, data)

        return decisions[entry_id]


def _normalize_publication_answer(answer: str, options: list[dict]) -> str | None:
    value = str(answer).strip().upper()
    option_ids = [str(option.get("id", "")) for option in options]

    if value in option_ids:
        return value

    if option_ids and all(option_id.isdigit() for option_id in option_ids):
        if len(value) == 1 and value in "ABCD":
            position = ord(value) - ord("A")
            return option_ids[position] if position < len(option_ids) else None

    if option_ids and all(len(option_id) == 1 and option_id.isalpha() for option_id in option_ids):
        if value.isdigit():
            position = int(value) - 1
            return option_ids[position] if 0 <= position < len(option_ids) else None

    return None


def create_publication(conversion_id: str) -> dict:
    with LOCK:
        data = read_job(conversion_id)

        if data.get("status") != "completed":
            raise ValueError("Conversion is not completed.")

        result = data.get("result") or {}
        review_decisions = data.get("review_decisions") or {}
        answer_key = data.get("answer_key") or {}
        answer_key_decisions = data.get("answer_key_decisions") or {}

        entries = answer_key.get("entries") or []
        entries_by_question = {}

        for entry in entries:
            question_id = entry.get("matched_question_id")

            if question_id:
                entries_by_question.setdefault(question_id, []).append(entry)

            for candidate_id in entry.get("candidate_question_ids") or []:
                entries_by_question.setdefault(candidate_id, []).append(entry)

        published_questions = []
        excluded_questions = []

        for section in result.get("sections") or []:
            for question in section.get("questions") or []:
                question_id = question.get("question_id")
                review_decision = review_decisions.get(question_id) or {}
                decision = review_decision.get("decision", "pending")

                reason = None

                if decision == "rejected":
                    reason = "Question was rejected during review."
                elif question.get("review_required") and decision != "approved":
                    reason = "Question requires review approval."

                related_entries = entries_by_question.get(question_id, [])

                if reason is None and related_entries:
                    if len(related_entries) != 1:
                        reason = "Answer-key mapping is ambiguous."
                    else:
                        entry = related_entries[0]
                        entry_decision = answer_key_decisions.get(
                            entry.get("entry_id"), {}
                        )

                        entry_status = entry.get("status")
                        entry_decision = answer_key_decisions.get(
                            entry.get("entry_id"), {}
                        )

                        is_approved = entry_decision.get("decision") == "approved"
                        corrected_answer = entry_decision.get("corrected_answer")

                        if entry_status == "matched":
                            if not is_approved:
                                reason = "Answer-key entry requires approval."

                        elif entry_status == "invalid":
                            if not is_approved or not corrected_answer:
                                reason = "Invalid answer-key entry requires an approved correction."

                        else:
                            reason = "Answer-key entry is not eligible."

                if reason:
                    excluded_questions.append({
                        "question_id": question_id,
                        "reason": reason,
                    })
                    continue

                published_question = deepcopy(question)

                if related_entries:
                    entry = related_entries[0]
                    entry_decision = answer_key_decisions.get(
                        entry.get("entry_id"), {}
                    )

                    corrected_answer = entry_decision.get("corrected_answer")

                    if corrected_answer:
                        normalized = _normalize_publication_answer(
                            corrected_answer,
                            published_question.get("options") or [],
                        )

                        if normalized is None:
                            excluded_questions.append({
                                "question_id": question_id,
                                "reason": "Approved answer correction does not match an option.",
                            })
                            continue

                        published_question["correct_answer"] = normalized

                published_questions.append({
                    **published_question,
                    "section_name": section.get("section_name"),
                })

        if not published_questions:
            raise ValueError("No eligible questions are available for publishing.")

        root = job_dir(conversion_id)
        publications_dir = root / "publications"
        publications_dir.mkdir(parents=True, exist_ok=True)

        existing_versions = [
            int(path.stem.split("-")[1])
            for path in publications_dir.glob("version-*.json")
            if path.stem.split("-")[-1].isdigit()
        ]

        version = max(existing_versions, default=0) + 1

        publication = {
            "publication_id": f"{conversion_id}-v{version}",
            "conversion_id": conversion_id,
            "version": version,
            "published_at": datetime.now(timezone.utc).isoformat(),
            "source_filename": (
                result.get("document", {}).get("source_filename")
            ),
            "total_questions": len(published_questions),
            "excluded_questions": excluded_questions,
            "questions": published_questions,
        }

        destination = publications_dir / f"version-{version:04d}.json"
        temporary = publications_dir / f"version-{version:04d}.tmp"

        temporary.write_text(
            json.dumps(publication, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(destination)

        return publication


def list_publications(conversion_id: str) -> list[dict]:
    with LOCK:
        publications_dir = job_dir(conversion_id) / "publications"

        if not publications_dir.is_dir():
            return []

        publications = []

        for path in publications_dir.glob("version-*.json"):
            try:
                publication = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue

            publications.append({
                "publication_id": publication.get("publication_id"),
                "conversion_id": conversion_id,
                "version": publication.get("version"),
                "published_at": publication.get("published_at"),
                "source_filename": publication.get("source_filename"),
                "total_questions": publication.get("total_questions"),
            })

        return sorted(
            publications,
            key=lambda item: item["version"],
            reverse=True,
        )


def read_publication(conversion_id: str, version: int) -> dict:
    with LOCK:
        if version < 1:
            raise FileNotFoundError("Publication not found.")

        path = (
            job_dir(conversion_id)
            / "publications"
            / f"version-{version:04d}.json"
        )

        if not path.is_file():
            raise FileNotFoundError("Publication not found.")

        return json.loads(path.read_text(encoding="utf-8"))


def get_analytics_overview(organization_id: str) -> dict:
    if not organization_id:
        raise ValueError("Organization ID is required.")

    jobs, total_jobs = list_jobs(
        limit=10000,
        offset=0,
        organization_id=organization_id,
    )

    document_status = {
        "completed": 0,
        "failed": 0,
        "processing": 0,
        "queued": 0,
        "other": 0,
    }

    total_questions = 0
    question_types = {}
    review_stats = {
        "pending": 0,
        "approved": 0,
        "rejected": 0,
    }

    answer_key_stats = {
        "total": 0,
        "by_status": {
            "matched": 0,
            "unmatched": 0,
            "ambiguous": 0,
            "duplicate": 0,
            "conflicting": 0,
            "invalid": 0,
        },
        "review": {
            "pending": 0,
            "approved": 0,
            "rejected": 0,
        },
    }

    publication_stats = {
        "versions": 0,
        "published_questions": 0,
        "excluded_questions": 0,
    }

    recent_documents = []

    for job in jobs:
        status = job.get("status") or "other"

        if status in document_status:
            document_status[status] += 1
        else:
            document_status["other"] += 1

        result = job.get("result") or {}
        document = result.get("document") or {}

        filename = (
            document.get("source_filename")
            or job.get("filename")
            or "Unknown document"
        )

        conversion_id = job.get("conversion_id")

        recent_documents.append({
            "conversion_id": conversion_id,
            "filename": filename,
            "status": status,
            "format": (
                document.get("source_format")
                or job.get("format")
            ),
            "total_questions": (
                document.get("total_questions") or 0
            ),    
        })

        if status != "completed":
            continue

        review_decisions = job.get("review_decisions") or {}

        for section in result.get("sections") or []:
            for question in section.get("questions") or []:
                total_questions += 1

                question_type = (
                    question.get("question_type") or "unclassified"
                )
                question_types[question_type] = (
                    question_types.get(question_type, 0) + 1
                )

                if question.get("review_required", False):
                    question_id = question.get("question_id")
                    saved_decision = (
                        review_decisions.get(question_id) or {}
                    )
                    decision = saved_decision.get("decision", "pending")

                    if decision in review_stats:
                        review_stats[decision] += 1
                    else:
                        review_stats["pending"] += 1

        answer_key = job.get("answer_key") or {}
        answer_key_decisions = job.get("answer_key_decisions") or {}

        for entry in answer_key.get("entries") or []:
            answer_key_stats["total"] += 1

            entry_status = entry.get("status") or "unclassified"

            if entry_status in answer_key_stats["by_status"]:
                answer_key_stats["by_status"][entry_status] += 1

            saved_decision = (
                answer_key_decisions.get(entry.get("entry_id")) or {}
            )
            decision = saved_decision.get("decision", "pending")

            if decision in answer_key_stats["review"]:
                answer_key_stats["review"][decision] += 1
            else:
                answer_key_stats["review"]["pending"] += 1

        if conversion_id:
            try:
                publications = list_publications(conversion_id)
            except (FileNotFoundError, OSError):
                publications = []

            publication_stats["versions"] += len(publications)

            for publication_summary in publications:
                try:
                    publication = read_publication(
                        conversion_id,
                        publication_summary["version"],
                    )
                except (FileNotFoundError, OSError, KeyError, ValueError):
                    continue

                publication_stats["published_questions"] += (
                    publication.get("total_questions") or 0
                )

                excluded = publication.get("excluded_questions") or []

                if isinstance(excluded, list):
                    publication_stats["excluded_questions"] += len(excluded)


    return {
        "documents": {
            "total": total_jobs,
            "by_status": document_status,
        },
        "questions": {
            "total": total_questions,
            "by_type": question_types,
            "review": review_stats,
        },
        "answer_keys": answer_key_stats,
        "publishing": publication_stats,
        "recent_documents": recent_documents[:10],
    }

