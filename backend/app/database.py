from pymongo import MongoClient
from pymongo.database import Database

from app.config import settings
from app.database_indexes import ensure_indexes

mongo_client: MongoClient | None = None
mongo_database: Database | None = None


def connect_to_mongo() -> Database:
    global mongo_client, mongo_database

    if mongo_client is not None:
        return mongo_database

    client = MongoClient(
        settings.mongodb_uri,
        serverSelectionTimeoutMS=5000,
    )

    try:
        client.admin.command("ping")
        db = client[settings.mongodb_database]
        ensure_indexes(db)
    except Exception:
        client.close()
        raise

    mongo_client = client
    mongo_database = db

    return mongo_database


def close_mongo_connection() -> None:
    global mongo_client, mongo_database

    if mongo_client is not None:
        mongo_client.close()

    mongo_client = None
    mongo_database = None


def get_database() -> Database:
    if mongo_database is None:
        raise RuntimeError(
            "MongoDB connection has not been initialized."
        )

    return mongo_database
