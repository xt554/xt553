import jwt
import pytest

from core.security import (
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip() -> None:
    encoded = hash_password("StrongPassword!123")
    assert encoded != "StrongPassword!123"
    assert verify_password("StrongPassword!123", encoded)
    assert not verify_password("wrong-password", encoded)


def test_access_token_roundtrip() -> None:
    token = create_access_token("user-id", "ADMIN")
    payload = decode_token(token)
    assert payload["sub"] == "user-id"
    assert payload["role"] == "ADMIN"
    assert payload["type"] == "access"


def test_refresh_token_rejected_as_access() -> None:
    token = create_refresh_token("user-id", "ADMIN")
    with pytest.raises(TokenError):
        decode_token(token)


def test_tampered_token_rejected() -> None:
    token = create_access_token("user-id", "ADMIN")
    parts = token.split(".")
    parts[1] = jwt.utils.base64url_encode(b'{"sub":"other"}').decode()
    with pytest.raises(TokenError):
        decode_token(".".join(parts))
