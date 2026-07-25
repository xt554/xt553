from __future__ import annotations

import hashlib
import hmac


def signer_signature(secret: str, timestamp: str, nonce: str, body: bytes) -> str:
    message = timestamp.encode() + b"\n" + nonce.encode() + b"\n" + body
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verify_signer_signature(
    secret: str,
    timestamp: str,
    nonce: str,
    body: bytes,
    signature: str,
) -> bool:
    expected = signer_signature(secret, timestamp, nonce, body)
    return hmac.compare_digest(expected, signature)
