
from dataclasses import dataclass

from fastapi import HTTPException, Request

from app.repositories.auth_repository import AuthRepository
from app.services.security import hash_session_token


SESSION_COOKIE = "neetday_session"


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user_id: str
    organization_id: str
    role: str


def get_auth_repository() -> AuthRepository:
    return AuthRepository()


def get_current_principal(
    request: Request,
) -> AuthenticatedPrincipal:
    raw_token = request.cookies.get(SESSION_COOKIE)

    if not raw_token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
        )

    repository = get_auth_repository()

    session = repository.find_session_by_token_hash(
        hash_session_token(raw_token)
    )

    if not session:
        raise HTTPException(
            status_code=401,
            detail="Session expired or invalid.",
        )

    user = repository.find_user_by_id(session["user_id"])

    if not user or not user.get("is_active", False):
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
        )

    membership = repository.find_active_membership(user["_id"])

    if not membership:
        raise HTTPException(
            status_code=403,
            detail="No active organization membership found.",
        )

    organization = repository.find_organization_by_id(
        membership["organization_id"]
    )

    if not organization:
        raise HTTPException(
            status_code=403,
            detail="Organization is unavailable.",
        )

    return AuthenticatedPrincipal(
        user_id=user["_id"],
        organization_id=organization["_id"],
        role=membership["role"],
    )
