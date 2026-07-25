from __future__ import annotations

import hashlib
from time import time

import pytest

from core.config import settings
from services.fragment_capture import FragmentPaymentRequest
from services.ton_signer import SignRequest, sign_and_broadcast


def test_capture_source_and_fingerprint() -> None:
    request = FragmentPaymentRequest.from_tonconnect(
        {
            "validUntil": int(time()) + 120,
            "network": "-239",
            "from": "UQDt7K7GNl48mpQtXKLzafD8Vv2gJtUPEvKDMp7Z0JkWtTWr",
            "messages": [
                {"address": "UQCj4dYYpzdTro70lUlYmu0wFfenSksjg1lDUINcIXh2p0cd", "amount": "1000000000", "payload": "dGVzdA=="}
            ],
        }
    )
    assert request.source_address == "UQDt7K7GNl48mpQtXKLzafD8Vv2gJtUPEvKDMp7Z0JkWtTWr"
    assert request.fingerprint == request.fingerprint
    assert len(request.fingerprint) == 64


@pytest.mark.asyncio
async def test_local_mock_is_not_broadcast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ton_signer_mode", "mock")
    payload_hash = hashlib.sha256(b"test").hexdigest()
    result = await sign_and_broadcast(
        SignRequest(
            request_id="frag_12345678",
            order_id="00000000-0000-0000-0000-000000000000",
            wallet_code="ton-hot-1",
            source_address="UQDt7K7GNl48mpQtXKLzafD8Vv2gJtUPEvKDMp7Z0JkWtTWr",
            destination="UQCj4dYYpzdTro70lUlYmu0wFfenSksjg1lDUINcIXh2p0cd",
            amount_nano=1_000_000_000,
            payload_boc="dGVzdA==",
            payload_hash=payload_hash,
            valid_until=int(time()) + 120,
            network="-239",
            idempotency_key="fragment:test:v2",
            expected_amount_nano=1_000_000_000,
            schema_hash="a" * 64,
        )
    )
    assert result.signer_mode == "local_mock"
    assert result.broadcasted is False
    assert result.external_message_hash.startswith("mock_")
