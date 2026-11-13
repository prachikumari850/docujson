
import base64
import hashlib
import hmac
import secrets

from app.config import settings


def generate_csrf_token() -> str:
    nonce = secrets.token_urlsafe(32)
    signature = hmac.new(
        settings.csrf_secret.encode("utf-8"),
        nonce.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return f"{nonce}.{encoded_signature}"


def verify_csrf_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False

    nonce, supplied_signature = token.rsplit(".", 1)

    if not nonce or not supplied_signature:
        return False

    expected_signature = hmac.new(
        settings.csrf_secret.encode("utf-8"),
        nonce.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    expected_encoded = (
        base64.urlsafe_b64encode(expected_signature)
        .decode("ascii")
        .rstrip("=")
    )

    return hmac.compare_digest(supplied_signature, expected_encoded)
