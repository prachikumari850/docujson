
import pytest
from fastapi.testclient import TestClient

from app import database
from app.main import app


def test_mongodb_connection():
    try:
        db = database.connect_to_mongo()

        assert db is not None
        assert db.name == "neetday"
        assert database.get_database() is db

    finally:
        database.close_mongo_connection()


def test_database_requires_initialized_connection():
    assert database.mongo_database is None

    with pytest.raises(RuntimeError):
        database.get_database()


def test_fastapi_lifespan_connects_and_closes_mongodb():
    with TestClient(app) as client:
        assert database.get_database().name == "neetday"

        response = client.get("/api/health")
        assert response.status_code == 200

    assert database.mongo_database is None
    assert database.mongo_client is None
