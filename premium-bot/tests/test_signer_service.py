from __future__ import annotations

import hashlib
import json
import secrets
import time

from fastapi.testclient import TestClient

from core.config import settings
from core.signer_auth import signer_signature
from signer.app import app


def test_remote_mock_signer_policy(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ton_signer_shared_secret", "test-secret-123456789")
    monkeypatch.setattr(settings, "ton_signer_backend", "mock")
    monkeypatch.setattr(settings, "ton_signer_wallet_codes", "ton-hot-1")
    monkeypatch.setattr(settings, "ton_signer_wallet_addresses", "ton-hot-1=UQDt7K7GNl48mpQtXKLzafD8Vv2gJtUPEvKDMp7Z0JkWtTWr")
    monkeypatch.setattr(settings, "ton_known_destinations", "UQCj4dYYpzdTro70lUlYmu0wFfenSksjg1lDUINcIXh2p0cd")
    monkeypatch.setattr(settings, "ton_require_source_match", True)

    body = json.dumps(
        {
            "request_id": "frag_12345678",
            "order_id": "00000000-0000-0000-0000-000000000000",
            "wallet_code": "ton-hot-1",
            "source_address": "UQDt7K7GNl48mpQtXKLzafD8Vv2gJtUPEvKDMp7Z0JkWtTWr",
            "destination": "UQCj4dYYpzdTro70lUlYmu0wFfenSksjg1lDUINcIXh2p0cd",
            "amount_nano": 1_000_000_000,
            "payload_boc": "dGVzdA==",
            "payload_hash": hashlib.sha256(b"test").hexdigest(),
            "valid_until": int(time.time()) + 120,
            "network": "-239",
            "idempotency_key": f"fragment:test:{secrets.token_hex(8)}",
            "expected_amount_nano": 1_000_000_000,
            "schema_hash": "a" * 64,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    signature = signer_signature(
        settings.ton_signer_shared_secret,
        timestamp,
        nonce,
        body,
    )
    response = TestClient(app).post(
        "/internal/v1/sign-and-broadcast",
        content=body,
        headers={
            "content-type": "application/json",
            "x-signer-timestamp": timestamp,
            "x-signer-nonce": nonce,
            "x-signer-signature": signature,
        },
    )
    assert response.status_code == 200
    assert response.json()["broadcasted"] is False
    assert response.json()["signer_mode"] == "remote_mock"
