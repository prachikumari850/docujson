
import mongomock
import pytest

from pymongo.errors import DuplicateKeyError

from app.database_indexes import ensure_indexes
from app.repositories.document_job_repository import (
    DocumentJobRepository,
)


@pytest.fixture
def repository():
    client = mongomock.MongoClient()
    database = client["document_job_test"]
    ensure_indexes(database)

    yield DocumentJobRepository(database=database)

    client.close()


def create_test_job(
    repository,
    conversion_id="a" * 32,
    organization_id="org-1",
    created_by="user-1",
):
    return repository.create_job(
        conversion_id=conversion_id,
        organization_id=organization_id,
        created_by=created_by,
    )


def test_create_job_creates_processing_job_and_document(repository):
    job = create_test_job(repository)

    assert job["conversion_id"] == "a" * 32
    assert job["organization_id"] == "org-1"
    assert job["created_by"] == "user-1"
    assert job["status"] == "queued"
    assert job["progress"] == 0
    assert job["stage"] == "Waiting to start"
    assert job["review_decisions"] == {}

    document = repository.documents.find_one(
        {"_id": "a" * 32}
    )

    assert document is not None
    assert document["organization_id"] == "org-1"
    assert document["filename"] is None
    assert document["format"] is None


def test_create_job_rolls_back_processing_job_if_document_insert_fails(
    repository,
):
    repository.documents.insert_one(
        {
            "_id": "a" * 32,
            "conversion_id": "a" * 32,
            "organization_id": "org-1",
        }
    )

    with pytest.raises(DuplicateKeyError):
        create_test_job(repository)

    assert repository.processing_jobs.find_one(
        {"_id": "a" * 32}
    ) is None


def test_get_job_returns_job_without_mongodb_id(repository):
    create_test_job(repository)

    job = repository.get_job("a" * 32)

    assert job is not None
    assert job["conversion_id"] == "a" * 32
    assert "_id" not in job


def test_get_job_returns_none_for_unknown_conversion(repository):
    assert repository.get_job("b" * 32) is None


def test_get_job_for_organization_enforces_tenant_scope(repository):
    create_test_job(repository)

    own_job = repository.get_job_for_organization(
        "a" * 32,
        "org-1",
    )
    other_job = repository.get_job_for_organization(
        "a" * 32,
        "org-2",
    )

    assert own_job is not None
    assert own_job["organization_id"] == "org-1"
    assert other_job is None


def test_update_job_updates_state_and_document_metadata(repository):
    create_test_job(repository)

    job = repository.update_job(
        "a" * 32,
        {
            "status": "completed",
            "progress": 100,
            "stage": "Conversion complete",
            "filename": "physics.pdf",
            "format": "pdf",
            "result": {"sections": []},
        },
    )

    assert job["status"] == "completed"
    assert job["progress"] == 100
    assert job["filename"] == "physics.pdf"
    assert job["format"] == "pdf"
    assert job["result"] == {"sections": []}

    document = repository.documents.find_one(
        {"_id": "a" * 32}
    )

    assert document["status"] == "completed"
    assert document["progress"] == 100
    assert document["filename"] == "physics.pdf"
    assert document["format"] == "pdf"


def test_update_job_does_not_modify_immutable_fields(repository):
    create_test_job(repository)

    job = repository.update_job(
        "a" * 32,
        {
            "organization_id": "org-2",
            "created_by": "user-2",
            "conversion_id": "b" * 32,
            "created_at": None,
            "status": "processing",
        },
    )

    assert job["organization_id"] == "org-1"
    assert job["created_by"] == "user-1"
    assert job["conversion_id"] == "a" * 32
    assert job["status"] == "processing"


def test_update_job_raises_for_unknown_conversion(repository):
    with pytest.raises(FileNotFoundError):
        repository.update_job(
            "a" * 32,
            {"status": "processing"},
        )


def test_list_jobs_returns_only_organization_jobs(repository):
    create_test_job(
        repository,
        conversion_id="a" * 32,
        organization_id="org-1",
    )
    create_test_job(
        repository,
        conversion_id="b" * 32,
        organization_id="org-2",
    )
    create_test_job(
        repository,
        conversion_id="c" * 32,
        organization_id="org-1",
    )

    jobs, total = repository.list_jobs(
        organization_id="org-1",
        limit=10,
        offset=0,
    )

    assert total == 2
    assert len(jobs) == 2
    assert all(job["organization_id"] == "org-1" for job in jobs)


def test_list_jobs_applies_pagination(repository):
    for index in range(3):
        create_test_job(
            repository,
            conversion_id=f"{index + 1:032x}",
        )

    jobs, total = repository.list_jobs(
        organization_id="org-1",
        limit=2,
        offset=1,
    )

    assert total == 3
    assert len(jobs) == 2


def test_delete_job_removes_only_matching_organization_job(repository):
    create_test_job(repository)

    assert repository.delete_job(
        "a" * 32,
        "org-2",
    ) is False

    assert repository.get_job("a" * 32) is not None

    assert repository.delete_job(
        "a" * 32,
        "org-1",
    ) is True

    assert repository.get_job("a" * 32) is None
    assert repository.documents.find_one(
        {"_id": "a" * 32}
    ) is None

def test_update_job_persists_failed_status_and_error(repository):
    create_test_job(repository)

    job = repository.update_job(
        "a" * 32,
        {
            "status": "failed",
            "progress": 100,
            "stage": "Conversion failed",
            "error": "Document extraction failed.",
            "result": None,
        },
    )

    assert job["status"] == "failed"
    assert job["progress"] == 100
    assert job["stage"] == "Conversion failed"
    assert job["error"] == "Document extraction failed."
    assert job["result"] is None

    document = repository.documents.find_one(
        {"_id": "a" * 32}
    )

    assert document["status"] == "failed"
    assert document["progress"] == 100
    assert document["stage"] == "Conversion failed"