
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from pymongo.errors import DuplicateKeyError

from app.repositories.auth_repository import (
    AuthRepository,
    generate_organization_slug,
    normalize_email,
    utc_now,
)


@pytest.fixture
def repository():
    database = MagicMock()

    return AuthRepository(database=database), database


def test_normalize_email():
    assert normalize_email("  USER@Example.COM ") == "user@example.com"


def test_generate_organization_slug():
    first = generate_organization_slug("ABC Academy")
    second = generate_organization_slug("ABC Academy")

    assert first.startswith("abc-academy-")
    assert second.startswith("abc-academy-")
    assert first != second


def test_registration_creates_user_organization_and_owner_membership(repository):
    repo, database = repository

    result = repo.create_registration(
        name="Test User",
        email="TEST@example.com",
        password_hash="$argon2id$test",
        organization_name="ABC Academy",
    )

    user = result["user"]
    organization = result["organization"]
    membership = result["membership"]

    assert user["email_normalized"] == "test@example.com"
    assert user["password_hash"] == "$argon2id$test"
    assert user["is_active"] is True

    assert organization["name"] == "ABC Academy"
    assert organization["slug"].startswith("abc-academy-")

    assert membership["user_id"] == user["_id"]
    assert membership["organization_id"] == organization["_id"]
    assert membership["role"] == "owner"
    assert membership["status"] == "active"

    database.users.insert_one.assert_called_once_with(user)
    database.organizations.insert_one.assert_called_once_with(organization)
    database.memberships.insert_one.assert_called_once_with(membership)


def test_registration_rolls_back_user_if_organization_insert_fails(repository):
    repo, database = repository

    database.organizations.insert_one.side_effect = RuntimeError(
        "Organization insert failed"
    )

    with pytest.raises(RuntimeError, match="Organization insert failed"):
        repo.create_registration(
            name="Test User",
            email="test@example.com",
            password_hash="$argon2id$test",
            organization_name="ABC Academy",
        )

    database.users.delete_one.assert_called_once()
    database.memberships.insert_one.assert_not_called()


def test_registration_rolls_back_user_and_organization_if_membership_fails(
    repository,
):
    repo, database = repository

    database.memberships.insert_one.side_effect = RuntimeError(
        "Membership insert failed"
    )

    with pytest.raises(RuntimeError, match="Membership insert failed"):
        repo.create_registration(
            name="Test User",
            email="test@example.com",
            password_hash="$argon2id$test",
            organization_name="ABC Academy",
        )

    database.users.delete_one.assert_called_once()
    database.organizations.delete_one.assert_called_once()


def test_duplicate_email_error_is_propagated(repository):
    repo, database = repository

    database.users.insert_one.side_effect = DuplicateKeyError(
        "Duplicate email"
    )

    with pytest.raises(DuplicateKeyError):
        repo.create_registration(
            name="Test User",
            email="existing@example.com",
            password_hash="$argon2id$test",
            organization_name="ABC Academy",
        )

    database.organizations.insert_one.assert_not_called()
    database.memberships.insert_one.assert_not_called()


def test_find_user_by_email_uses_normalized_email(repository):
    repo, database = repository
    database.users.find_one.return_value = {"_id": "user-123"}

    result = repo.find_user_by_email(" USER@Example.COM ")

    assert result == {"_id": "user-123"}
    database.users.find_one.assert_called_once_with(
        {"email_normalized": "user@example.com"}
    )


def test_find_user_by_id(repository):
    repo, database = repository
    database.users.find_one.return_value = {"_id": "user-123"}

    result = repo.find_user_by_id("user-123")

    assert result == {"_id": "user-123"}
    database.users.find_one.assert_called_once_with({"_id": "user-123"})


def test_create_session_stores_token_hash(repository):
    repo, database = repository
    expires_at = utc_now() + timedelta(hours=24)

    session = repo.create_session(
        user_id="user-123",
        token_hash="hashed-token",
        expires_at=expires_at,
    )

    assert session["user_id"] == "user-123"
    assert session["token_hash"] == "hashed-token"
    assert session["expires_at"] == expires_at
    assert "token" not in session

    database.sessions.insert_one.assert_called_once_with(session)


def test_find_session_requires_unexpired_session(repository):
    repo, database = repository
    database.sessions.find_one.return_value = {"_id": "session-123"}

    result = repo.find_session_by_token_hash("hashed-token")

    assert result == {"_id": "session-123"}

    query = database.sessions.find_one.call_args.args[0]

    assert query["token_hash"] == "hashed-token"
    assert "$gt" in query["expires_at"]


def test_revoke_session_returns_true_when_deleted(repository):
    repo, database = repository
    database.sessions.delete_one.return_value.deleted_count = 1

    assert repo.revoke_session("hashed-token") is True

    database.sessions.delete_one.assert_called_once_with(
        {"token_hash": "hashed-token"}
    )


def test_revoke_session_returns_false_when_not_found(repository):
    repo, database = repository
    database.sessions.delete_one.return_value.deleted_count = 0

    assert repo.revoke_session("unknown-token") is False
