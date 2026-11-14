
from copy import deepcopy
from datetime import datetime, timezone

from pymongo.collection import Collection
from pymongo.database import Database

from app.database import get_database


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DocumentJobRepository:
    IMMUTABLE_FIELDS = {
        "_id",
        "conversion_id",
        "organization_id",
        "created_by",
        "created_at",
    }

    def __init__(self, database: Database | None = None):
        self.database = database or get_database()
        self.documents: Collection = self.database.documents
        self.processing_jobs: Collection = self.database.processing_jobs

    @staticmethod
    def _serialize(document: dict | None) -> dict | None:
        if document is None:
            return None

        data = deepcopy(document)
        data.pop("_id", None)
        return data

    def create_job(
        self,
        conversion_id: str,
        organization_id: str,
        created_by: str,
    ) -> dict:
        now = utc_now()

        job = {
            "_id": conversion_id,
            "conversion_id": conversion_id,
            "organization_id": organization_id,
            "created_by": created_by,
            "status": "queued",
            "progress": 0,
            "stage": "Waiting to start",
            "error": None,
            "result": None,
            "review_decisions": {},
            "answer_key": None,
            "answer_key_decisions": {},
            "created_at": now,
            "updated_at": now,
        }

        document = {
            "_id": conversion_id,
            "conversion_id": conversion_id,
            "organization_id": organization_id,
            "created_by": created_by,
            "filename": None,
            "format": None,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
        }

        self.processing_jobs.insert_one(job)

        try:
            self.documents.insert_one(document)
        except Exception:
            self.processing_jobs.delete_one({"_id": conversion_id})
            raise

        return self._serialize(job)

    def get_job(self, conversion_id: str) -> dict | None:
        job = self.processing_jobs.find_one(
            {"_id": conversion_id}
        )
        return self._serialize(job)

    def get_job_for_organization(
        self,
        conversion_id: str,
        organization_id: str,
    ) -> dict | None:
        job = self.processing_jobs.find_one(
            {
                "_id": conversion_id,
                "organization_id": organization_id,
            }
        )
        return self._serialize(job)

    def update_job(
        self,
        conversion_id: str,
        values: dict,
    ) -> dict:
        updates = {
            key: deepcopy(value)
            for key, value in values.items()
            if key not in self.IMMUTABLE_FIELDS
        }

        if not updates:
            job = self.get_job(conversion_id)
            if job is None:
                raise FileNotFoundError("Conversion not found.")
            return job

        updates["updated_at"] = utc_now()

        result = self.processing_jobs.update_one(
            {"_id": conversion_id},
            {"$set": updates},
        )

        if result.matched_count != 1:
            raise FileNotFoundError("Conversion not found.")

        metadata_fields = {
            key: updates[key]
            for key in (
                "filename",
                "format",
                "status",
                "progress",
                "stage",
            )
            if key in updates
        }

        if metadata_fields:
            metadata_fields["updated_at"] = updates["updated_at"]

            self.documents.update_one(
                {"_id": conversion_id},
                {"$set": metadata_fields},
            )

        job = self.get_job(conversion_id)

        if job is None:
            raise FileNotFoundError("Conversion not found.")

        return job

    def delete_job(
        self,
        conversion_id: str,
        organization_id: str,
    ) -> bool:
        query = {
            "_id": conversion_id,
            "organization_id": organization_id,
        }

        job_result = self.processing_jobs.delete_one(query)

        self.documents.delete_one(query)

        return job_result.deleted_count == 1

    def list_jobs(
        self,
        organization_id: str,
        limit: int,
        offset: int,
    ) -> tuple[list[dict], int]:
        query = {"organization_id": organization_id}

        total = self.processing_jobs.count_documents(query)

        cursor = (
            self.processing_jobs.find(query)
            .sort("created_at", -1)
            .skip(offset)
            .limit(limit)
        )

        jobs = [
            self._serialize(job)
            for job in cursor
        ]

        return jobs, total
