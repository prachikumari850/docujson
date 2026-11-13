
import re
import secrets
from datetime import datetime, timezone
from uuid import uuid4

from pymongo.collection import Collection
from pymongo.database import Database

from app.database import get_database


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def generate_organization_slug(name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    base = base or "organization"

    return f"{base}-{secrets.token_hex(3)}"


class AuthRepository:
    def __init__(self, database: Database | None = None):
        self.database = database or get_database()

        self.users: Collection = self.database.users
        self.organizations: Collection = self.database.organizations
        self.memberships: Collection = self.database.memberships
        self.sessions: Collection = self.database.sessions

    def find_user_by_email(self, email: str) -> dict | None:
        return self.users.find_one(
            {"email_normalized": normalize_email(email)}
        )

    def find_user_by_id(self, user_id: str) -> dict | None:
        return self.users.find_one({"_id": user_id})

    
    def find_active_membership(self, user_id: str) -> dict | None:
        return self.memberships.find_one(
            {
                "user_id": user_id,
                "status": "active",
            }
        )

    def find_organization_by_id(
        self,
        organization_id: str,
    ) -> dict | None:
        return self.organizations.find_one(
            {"_id": organization_id}
        )


    def create_registration(
        self,
        name: str,
        email: str,
        password_hash: str,
        organization_name: str,
    ) -> dict:
        now = utc_now()

        user_id = str(uuid4())
        organization_id = str(uuid4())
        membership_id = str(uuid4())

        user = {
            "_id": user_id,
            "name": name.strip(),
            "email": email.strip(),
            "email_normalized": normalize_email(email),
            "password_hash": password_hash,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }

        organization = {
            "_id": organization_id,
            "name": organization_name.strip(),
            "slug": generate_organization_slug(organization_name),
            "created_at": now,
            "updated_at": now,
        }

        membership = {
            "_id": membership_id,
            "organization_id": organization_id,
            "user_id": user_id,
            "role": "owner",
            "status": "active",
            "created_at": now,
        }

        inserted = []

        try:
            self.users.insert_one(user)
            inserted.append((self.users, user_id))

            self.organizations.insert_one(organization)
            inserted.append((self.organizations, organization_id))

            self.memberships.insert_one(membership)
            inserted.append((self.memberships, membership_id))

        except Exception:
            for collection, document_id in reversed(inserted):
                collection.delete_one({"_id": document_id})
            raise

        return {
            "user": user,
            "organization": organization,
            "membership": membership,
        }

    def create_session(
        self,
        user_id: str,
        token_hash: str,
        expires_at: datetime,
    ) -> dict:
        now = utc_now()

        session = {
            "_id": str(uuid4()),
            "user_id": user_id,
            "token_hash": token_hash,
            "created_at": now,
            "expires_at": expires_at,
            "last_seen_at": now,
        }

        self.sessions.insert_one(session)

        return session

    def find_session_by_token_hash(
        self,
        token_hash: str,
    ) -> dict | None:
        now = utc_now()

        return self.sessions.find_one(
            {
                "token_hash": token_hash,
                "expires_at": {"$gt": now},
            }
        )

    def revoke_session(self, token_hash: str) -> bool:
        result = self.sessions.delete_one(
            {"token_hash": token_hash}
        )

        return result.deleted_count == 1
