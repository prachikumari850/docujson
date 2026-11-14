
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from bson import BSON
from pymongo import MongoClient

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)

from app.config import settings


CONVERSION_ID = "f179b9bf39dd438ca728403b70257dbe"
ORGANIZATION_ID = "1f67a1b2-d8aa-47b3-84c6-8b2ac9eb80f8"
CREATED_BY = "96a5d7fd-71e1-4872-9db4-17a0fd411ff2"

SOURCE = settings.storage_path / CONVERSION_ID / "status.json"


def build_documents(source):
    source_mtime = SOURCE.stat().st_mtime
    timestamp = datetime.fromtimestamp(
        source_mtime,
        tz=timezone.utc,
    )

    job = dict(source)
    job["_id"] = CONVERSION_ID
    job["created_at"] = timestamp
    job["updated_at"] = timestamp

    result = source.get("result") or {}
    result_document = result.get("document") or {}

    document = {
        "_id": CONVERSION_ID,
        "conversion_id": CONVERSION_ID,
        "organization_id": ORGANIZATION_ID,
        "created_by": CREATED_BY,
        "filename": (
            source.get("filename")
            or result_document.get("source_filename")
        ),
        "format": (
            source.get("format")
            or result_document.get("source_format")
        ),
        "status": source.get("status"),
        "progress": source.get("progress", 0),
        "stage": source.get("stage"),
        "created_at": timestamp,
        "updated_at": timestamp,
    }

    return job, document


def main():
    parser = argparse.ArgumentParser(
        description="Migrate verified legacy NEETDAY jobs."
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate without modifying MongoDB.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Insert the verified records into MongoDB.",
    )

    args = parser.parse_args()

    print(
        "NEETDAY legacy job migration — "
        + ("DRY RUN" if args.dry_run else "APPLY")
    )
    print("-" * 50)

    if not SOURCE.is_file():
        raise FileNotFoundError(
            f"Source status file not found: {SOURCE}"
        )

    with SOURCE.open("r", encoding="utf-8") as file:
        source = json.load(file)

    if not isinstance(source, dict):
        raise ValueError("Source status must be a JSON object.")

    expected_values = {
        "conversion_id": CONVERSION_ID,
        "organization_id": ORGANIZATION_ID,
        "created_by": CREATED_BY,
    }

    for field, expected in expected_values.items():
        if source.get(field) != expected:
            raise ValueError(
                f"Ownership verification failed for {field}."
            )

    if source.get("status") != "completed":
        raise ValueError("Only completed jobs are eligible.")

    job, document = build_documents(source)

    job_bson = BSON.encode(job)
    document_bson = BSON.encode(document)

    client = MongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=5000,
    )

    job_inserted = False
    document_inserted = False

    try:
        client.admin.command("ping")
        database = client[settings.mongodb_database]

        organization = database.organizations.find_one(
            {"_id": ORGANIZATION_ID}
        )

        if organization is None:
            raise ValueError("JIMS organization does not exist.")

        membership = database.memberships.find_one(
            {
                "organization_id": ORGANIZATION_ID,
                "user_id": CREATED_BY,
                "status": "active",
                "role": "owner",
            }
        )

        if membership is None:
            raise ValueError(
                "The creator's active JIMS owner membership "
                "could not be verified."
            )

        if database.processing_jobs.find_one(
            {"_id": CONVERSION_ID}
        ):
            raise ValueError(
                "Processing job already exists. No overwrite allowed."
            )

        if database.documents.find_one(
            {"_id": CONVERSION_ID}
        ):
            raise ValueError(
                "Document record already exists. No overwrite allowed."
            )

        print("Source validation: PASSED")
        print("Organization verification: PASSED")
        print("Creator membership verification: PASSED")
        print("Duplicate check: PASSED")
        print("BSON serialization: PASSED")

        print()
        print(f"Conversion ID: {CONVERSION_ID}")
        print(f"Organization: {organization.get('name')}")
        print(f"Filename: {document['filename']}")
        print(f"Status: {document['status']}")
        print(f"Processing job BSON: {len(job_bson) / 1024 / 1024:.2f} MB")
        print(f"Document BSON: {len(document_bson) / 1024:.2f} KB")

        if args.dry_run:
            print()
            print("DRY RUN PASSED")
            print("No MongoDB records were inserted or modified.")
            return

        try:
            database.processing_jobs.insert_one(job)
            job_inserted = True

            database.documents.insert_one(document)
            document_inserted = True

            saved_job = database.processing_jobs.find_one(
                {
                    "_id": CONVERSION_ID,
                    "organization_id": ORGANIZATION_ID,
                }
            )

            saved_document = database.documents.find_one(
                {
                    "_id": CONVERSION_ID,
                    "organization_id": ORGANIZATION_ID,
                }
            )

            if saved_job is None or saved_document is None:
                raise RuntimeError(
                    "Post-insert verification failed."
                )

            if saved_job.get("result") != source.get("result"):
                raise RuntimeError(
                    "Extracted result verification failed."
                )

            if saved_job.get("answer_key") != source.get("answer_key"):
                raise RuntimeError(
                    "Answer-key verification failed."
                )

        except Exception:
            if document_inserted:
                database.documents.delete_one(
                    {
                        "_id": CONVERSION_ID,
                        "organization_id": ORGANIZATION_ID,
                    }
                )

            if job_inserted:
                database.processing_jobs.delete_one(
                    {
                        "_id": CONVERSION_ID,
                        "organization_id": ORGANIZATION_ID,
                    }
                )

            raise

        print()
        print("MIGRATION PASSED")
        print("Processing job inserted and verified.")
        print("Document metadata inserted and verified.")
        print("Original local files were not modified.")

    finally:
        client.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"\nMIGRATION FAILED: {error}")
        sys.exit(1)
