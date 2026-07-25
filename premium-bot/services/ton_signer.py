from __future__ import annotations

import hashlib
import json
import secrets
import time
from dataclasses import asdict, dataclass

import httpx

from core.config import settings
from core.signer_auth import signer_signature


class SignerUnavailable(RuntimeError):
    pass


class SignerRejected(RuntimeError):
    pass


@dataclass(frozen=True)
class SignRequest:
    request_id: str
    order_id: str
    wallet_code: str
    source_address: str | None
    destination: str
    amount_nano: int
    payload_boc: str
    payload_hash: str
    valid_until: int
    network: str
    idempotency_key: str
    expected_amount_nano: int
    schema_hash: str


@dataclass(frozen=True)
class SignResult:
    external_message_hash: str
    seqno: int | None
    broadcasted: bool
    signer_mode: str
    raw_result: dict[str, object]


def _local_mock(request: SignRequest) -> SignResult:
    digest = hashlib.sha256(
        f"{request.idempotency_key}:{request.wallet_code}:{request.payload_hash}".encode()
    ).hexdigest()
    return SignResult(
        external_message_hash=f"mock_{digest}",
        seqno=None,
        broadcasted=False,
        signer_mode="local_mock",
        raw_result={"mode": "local_mock", "broadcast": False},
    )


async def _remote_sign(request: SignRequest) -> SignResult:
    payload = asdict(request)
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(16)
    signature = signer_signature(
        settings.ton_signer_shared_secret,
        timestamp,
        nonce,
        body,
    )
    headers = {
        "content-type": "application/json",
        "x-signer-timestamp": timestamp,
        "x-signer-nonce": nonce,
        "x-signer-signature": signature,
    }
    url = f"{settings.ton_signer_url.rstrip('/')}/internal/v1/sign-and-broadcast"
    try:
        async with httpx.AsyncClient(timeout=settings.ton_signer_timeout_seconds) as client:
            response = await client.post(url, content=body, headers=headers)
    except httpx.HTTPError as exc:
        raise SignerUnavailable(f"TON signer request failed: {exc}") from exc
    if response.status_code >= 500:
        raise SignerUnavailable(f"TON signer unavailable: HTTP {response.status_code}")
    if response.status_code >= 400:
        detail = response.text[:500]
        raise SignerRejected(f"TON signer rejected request: HTTP {response.status_code}: {detail}")
    try:
        data = response.json()
        return SignResult(
            external_message_hash=str(data["external_message_hash"]),
            seqno=int(data["seqno"]) if data.get("seqno") is not None else None,
            broadcasted=bool(data.get("broadcasted")),
            signer_mode=str(data.get("signer_mode") or "remote"),
            raw_result=dict(data.get("raw_result") or {}),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SignerUnavailable("TON signer returned an invalid response") from exc


async def sign_and_broadcast(request: SignRequest) -> SignResult:
    """Call the signer boundary without exposing secret material to the API service.

    ``mock`` is a local deterministic simulation. ``remote`` and ``remote_mock``
    call the isolated signer service. Any other mode fails closed.
    """
    mode = settings.ton_signer_mode.lower()
    if mode in {"mock", "local_mock"}:
        return _local_mock(request)
    if mode in {"remote", "remote_mock"}:
        return await _remote_sign(request)
    raise SignerUnavailable("TON signer mode is disabled or unsupported")
