
import re

import pytest

from app.services.security import (
    generate_session_token,
    hash_password,
    hash_session_token,
    password_hash_needs_rehash,
    verify_password,
)


def test_password_is_stored_as_argon2_hash():
    password_hash = hash_password("TestPassword123!")

    assert password_hash.startswith("$argon2id$")
    assert password_hash != "TestPassword123!"


def test_correct_password_verifies():
    password_hash = hash_password("TestPassword123!")

    assert verify_password("TestPassword123!", password_hash) is True


def test_incorrect_password_is_rejected():
    password_hash = hash_password("TestPassword123!")

    assert verify_password("WrongPassword123!", password_hash) is False


@pytest.mark.parametrize("password", ["", None])
def test_empty_or_missing_password_is_rejected(password):
    with pytest.raises(ValueError):
        hash_password(password)


def test_malformed_password_hash_is_rejected():
    assert verify_password("TestPassword123!", "invalid-hash") is False


def test_password_hash_rehash_check():
    password_hash = hash_password("TestPassword123!")

    assert password_hash_needs_rehash(password_hash) is False
    assert password_hash_needs_rehash("invalid-hash") is False


def test_session_tokens_are_unique():
    first_token = generate_session_token()
    second_token = generate_session_token()

    assert first_token != second_token
    assert len(first_token) >= 40


def test_session_token_hash_is_sha256_hex():
    token = generate_session_token()
    token_hash = hash_session_token(token)

    assert re.fullmatch(r"[a-f0-9]{64}", token_hash)


def test_same_session_token_produces_same_hash():
    token = generate_session_token()

    assert hash_session_token(token) == hash_session_token(token)


def test_raw_session_token_is_not_equal_to_its_hash():
    token = generate_session_token()

    assert token != hash_session_token(token)


def test_empty_session_token_is_rejected():
    with pytest.raises(ValueError):
        hash_session_token("")
