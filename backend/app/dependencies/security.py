
import hmac

from fastapi import HTTPException, Request

from app.services.csrf import verify_csrf_token


CSRF_COOKIE = "neetday_csrf"


def require_csrf(request: Request) -> None:
    cookie_token = request.cookies.get(CSRF_COOKIE)
    header_token = request.headers.get("X-CSRF-Token")

    if (
        not cookie_token
        or not header_token
        or not hmac.compare_digest(cookie_token, header_token)
        or not verify_csrf_token(cookie_token)
    ):
        raise HTTPException(
            status_code=403,
            detail="Invalid or missing CSRF token.",
        )
