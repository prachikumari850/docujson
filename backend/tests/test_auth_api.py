
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers.auth import get_auth_repository
from app.services.security import hash_password, hash_session_token


@pytest.fixture
def repository():
    return MagicMock()


@pytest.fixture
def client(repository):
    app.dependency_overrides[get_auth_repository] = lambda: repository

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def csrf_headers(client):
    response = client.get("/api/auth/csrf")

    assert response.status_code == 200

    return {"X-CSRF-Token": response.json()["csrf_token"]}


def make_user():
    return {
        "_id": "user-123",
        "name": "Test User",
        "email": "test@example.com",
        "email_normalized": "test@example.com",
        "password_hash": hash_password("TestPassword123!"),
        "is_active": True,
    }


def make_organization():
    return {
        "_id": "org-123",
        "name": "ABC Academy",
        "slug": "abc-academy-123",
    }


def make_membership():
    return {
        "_id": "membership-123",
        "user_id": "user-123",
        "organization_id": "org-123",
        "role": "owner",
        "status": "active",
    }


def test_get_csrf_token(client):
    response = client.get("/api/auth/csrf")

    assert response.status_code == 200
    assert response.json()["csrf_token"]
    assert "neetday_csrf" in response.cookies


def test_register_success(client, repository, csrf_headers):
    repository.find_user_by_email.return_value = None

    repository.create_registration.return_value = {
        "user": make_user(),
        "organization": make_organization(),
        "membership": make_membership(),
    }

    response = client.post(
        "/api/auth/register",
        headers=csrf_headers,
        json={
            "name": "Test User",
            "email": "test@example.com",
            "password": "TestPassword123!",
            "organization_name": "ABC Academy",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["authenticated"] is True
    assert body["user"]["email"] == "test@example.com"
    assert body["organization"]["name"] == "ABC Academy"
    assert body["organization"]["role"] == "owner"

    assert "password_hash" not in response.text
    assert "neetday_session" in response.cookies
    assert response.cookies.get("neetday_session")


def test_register_rejects_duplicate_email(client, repository, csrf_headers):
    repository.find_user_by_email.return_value = make_user()

    response = client.post(
        "/api/auth/register",
        headers=csrf_headers,
        json={
            "name": "Test User",
            "email": "test@example.com",
            "password": "TestPassword123!",
            "organization_name": "ABC Academy",
        },
    )

    assert response.status_code == 409
    repository.create_registration.assert_not_called()


def test_register_rejects_missing_csrf_token(client):
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Test User",
            "email": "test@example.com",
            "password": "TestPassword123!",
            "organization_name": "ABC Academy",
        },
    )

    assert response.status_code == 403


def test_login_success(client, repository, csrf_headers):
    repository.find_user_by_email.return_value = make_user()
    repository.find_active_membership.return_value = make_membership()
    repository.find_organization_by_id.return_value = make_organization()

    response = client.post(
        "/api/auth/login",
        headers=csrf_headers,
        json={
            "email": "TEST@example.com",
            "password": "TestPassword123!",
        },
    )

    assert response.status_code == 200
    assert response.json()["user"]["id"] == "user-123"
    assert response.json()["organization"]["role"] == "owner"
    assert response.cookies.get("neetday_session")


def test_login_rejects_invalid_password(client, repository, csrf_headers):
    repository.find_user_by_email.return_value = make_user()

    response = client.post(
        "/api/auth/login",
        headers=csrf_headers,
        json={
            "email": "test@example.com",
            "password": "WrongPassword123!",
        },
    )

    assert response.status_code == 401


def test_login_rejects_inactive_user(client, repository, csrf_headers):
    user = make_user()
    user["is_active"] = False
    repository.find_user_by_email.return_value = user

    response = client.post(
        "/api/auth/login",
        headers=csrf_headers,
        json={
            "email": "test@example.com",
            "password": "TestPassword123!",
        },
    )

    assert response.status_code == 403


def test_login_rejects_missing_csrf_token(client):
    response = client.post(
        "/api/auth/login",
        json={
            "email": "test@example.com",
            "password": "TestPassword123!",
        },
    )

    assert response.status_code == 403


def test_me_returns_authenticated_user(client, repository):
    raw_token = "test-session-token"

    repository.find_session_by_token_hash.return_value = {
        "_id": "session-123",
        "user_id": "user-123",
        "expires_at": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    repository.find_user_by_id.return_value = make_user()
    repository.find_active_membership.return_value = make_membership()
    repository.find_organization_by_id.return_value = make_organization()

    client.cookies.set("neetday_session", raw_token)

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["user"]["email"] == "test@example.com"

    repository.find_session_by_token_hash.assert_called_once_with(
        hash_session_token(raw_token)
    )


def test_me_rejects_missing_session(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_me_rejects_invalid_session(client, repository):
    repository.find_session_by_token_hash.return_value = None

    client.cookies.set("neetday_session", "invalid-session")

    response = client.get("/api/auth/me")

    assert response.status_code == 401


def test_logout_revokes_session(client, repository, csrf_headers):
    raw_token = "test-session-token"
    client.cookies.set("neetday_session", raw_token)

    response = client.post(
        "/api/auth/logout",
        headers=csrf_headers,
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Logged out successfully."

    repository.revoke_session.assert_called_once_with(
        hash_session_token(raw_token)
    )


def test_logout_rejects_missing_csrf_token(client):
    response = client.post("/api/auth/logout")

    assert response.status_code == 403
