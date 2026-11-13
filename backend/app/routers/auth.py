
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pymongo.errors import DuplicateKeyError

from app.config import settings
from app.dependencies.auth import (
    SESSION_COOKIE,
    get_auth_repository,
)
from app.dependencies.security import require_csrf
from app.repositories.auth_repository import AuthRepository
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    OrganizationResponse,
    RegisterRequest,
    UserResponse,
)
from app.services.csrf import generate_csrf_token
from app.services.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    verify_password,
)


router = APIRouter(prefix="/api/auth", tags=["Authentication"])

CSRF_COOKIE = "neetday_csrf"


def set_csrf_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=CSRF_COOKIE,
        value=token,
        max_age=3600,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_same_site,
        path="/",
    )


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=settings.session_expire_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_same_site,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite=settings.cookie_same_site,
    )
    response.delete_cookie(
        key=CSRF_COOKIE,
        path="/",
        secure=settings.cookie_secure,
        httponly=False,
        samesite=settings.cookie_same_site,
    )


def build_auth_response(
    user: dict,
    organization: dict,
    membership: dict,
) -> AuthResponse:
    return AuthResponse(
        user=UserResponse(
            id=user["_id"],
            name=user["name"],
            email=user["email"],
        ),
        organization=OrganizationResponse(
            id=organization["_id"],
            name=organization["name"],
            slug=organization["slug"],
            role=membership["role"],
        ),
    )


def create_user_session(
    response: Response,
    repository: AuthRepository,
    user_id: str,
) -> None:
    raw_token = generate_session_token()
    token_hash = hash_session_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(
        hours=settings.session_expire_hours
    )

    repository.create_session(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=expires_at,
    )

    set_session_cookie(response, raw_token)


@router.get("/csrf")
def get_csrf_token(response: Response) -> dict:
    token = generate_csrf_token()
    set_csrf_cookie(response, token)

    return {"csrf_token": token}


@router.post(
    "/register",
    response_model=AuthResponse,
    dependencies=[Depends(require_csrf)],
)
def register(
    payload: RegisterRequest,
    response: Response,
    repository: AuthRepository = Depends(get_auth_repository),
):
    if repository.find_user_by_email(payload.email):
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists.",
        )

    password_hash = hash_password(payload.password)

    try:
        registration = repository.create_registration(
            name=payload.name,
            email=payload.email,
            password_hash=password_hash,
            organization_name=payload.organization_name,
        )
    except DuplicateKeyError:
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists.",
        )

    create_user_session(
        response,
        repository,
        registration["user"]["_id"],
    )

    return build_auth_response(
        registration["user"],
        registration["organization"],
        registration["membership"],
    )


@router.post(
    "/login",
    response_model=AuthResponse,
    dependencies=[Depends(require_csrf)],
)
def login(
    payload: LoginRequest,
    response: Response,
    repository: AuthRepository = Depends(get_auth_repository),
):
    user = repository.find_user_by_email(payload.email)

    if not user or not verify_password(
        payload.password,
        user.get("password_hash", ""),
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid email or password.",
        )

    if not user.get("is_active", False):
        raise HTTPException(
            status_code=403,
            detail="This account is inactive.",
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

    create_user_session(response, repository, user["_id"])

    return build_auth_response(user, organization, membership)


@router.get("/me", response_model=AuthResponse)
def get_current_user(
    request: Request,
    response: Response,
    repository: AuthRepository = Depends(get_auth_repository),
):
    raw_token = request.cookies.get(SESSION_COOKIE)

    if not raw_token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
        )

    session = repository.find_session_by_token_hash(
        hash_session_token(raw_token)
    )

    if not session:
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=401,
            detail="Session expired or invalid.",
        )

    user = repository.find_user_by_id(session["user_id"])

    if not user or not user.get("is_active", False):
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
        )

    membership = repository.find_active_membership(user["_id"])

    if not membership:
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=403,
            detail="No active organization membership found.",
        )

    organization = repository.find_organization_by_id(
        membership["organization_id"]
    )

    if not organization:
        clear_auth_cookies(response)
        raise HTTPException(
            status_code=403,
            detail="Organization is unavailable.",
        )

    return build_auth_response(user, organization, membership)


@router.post(
    "/logout",
    dependencies=[Depends(require_csrf)],
)
def logout(
    request: Request,
    response: Response,
    repository: AuthRepository = Depends(get_auth_repository),
):
    raw_token = request.cookies.get(SESSION_COOKIE)

    if raw_token:
        repository.revoke_session(
            hash_session_token(raw_token)
        )

    clear_auth_cookies(response)

    return {"message": "Logged out successfully."}
