from __future__ import annotations

import asyncio
import base64
import hashlib
import time
from collections import OrderedDict

from fastapi import FastAPI, Header, HTTPException, Request, status
from pydantic import ValidationError

from core.config import settings
from core.signer_auth import verify_signer_signature
from services.ton_units import ton_to_nano
from services.ton_address import normalize_ton_address
from signer.schemas import SignerRequest, SignerResponse

app = FastAPI(title="Premium Bot TON Signer", docs_url=None, redoc_url=None)
_nonce_lock = asyncio.Lock()
_seen_nonces: OrderedDict[str, int] = OrderedDict()
_idempotency_results: OrderedDict[str, SignerResponse] = OrderedDict()
_MAX_CACHE = 10_000


async def _accept_nonce(nonce: str, timestamp: int) -> bool:
    async with _nonce_lock:
        cutoff = int(time.time()) - max(300, settings.ton_signer_max_clock_skew_seconds * 3)
        for key in list(_seen_nonces):
            if _seen_nonces[key] >= cutoff:
                break
            _seen_nonces.pop(key, None)
        if nonce in _seen_nonces:
            return False
        _seen_nonces[nonce] = timestamp
        while len(_seen_nonces) > _MAX_CACHE:
            _seen_nonces.popitem(last=False)
        return True


def _validate_policy(payload: SignerRequest) -> None:
    if payload.network != "-239":
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Only TON mainnet is allowed")
    if payload.wallet_code not in settings.ton_signer_wallet_code_list:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Wallet code is not approved")
    wallet_addresses = settings.ton_signer_wallet_address_map
    expected_source = wallet_addresses.get(payload.wallet_code)
    if settings.ton_require_source_match:
        if not expected_source:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Signer wallet address map is not configured",
            )
        if payload.source_address and normalize_ton_address(payload.source_address) != normalize_ton_address(expected_source):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "TON Connect source does not match signer wallet",
            )
    if settings.ton_destination_policy.lower() == "exact" or settings.ton_require_exact_destination:
        approved = {normalize_ton_address(v) for v in settings.ton_known_destination_list}
        if normalize_ton_address(payload.destination) not in approved:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Destination is not approved by signer policy")
    if payload.amount_nano > ton_to_nano(settings.ton_single_limit):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Signer single limit exceeded")
    deviation_bps = abs(payload.amount_nano - payload.expected_amount_nano) * 10_000 // max(1, payload.expected_amount_nano)
    if deviation_bps > settings.ton_amount_deviation_bps:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Signer quote deviation exceeded")
    now = int(time.time())
    ttl = payload.valid_until - now
    if ttl < settings.fragment_capture_min_ttl_seconds:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Request is expired")
    if ttl > settings.fragment_capture_max_ttl_seconds:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Request TTL is too long")
    try:
        raw_payload = base64.b64decode(payload.payload_boc, validate=True)
    except Exception:
        raw_payload = payload.payload_boc.encode()
    digest = hashlib.sha256(raw_payload).hexdigest()
    if digest != payload.payload_hash:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Payload hash mismatch")


@app.get("/health/live")
async def health_live() -> dict[str, str]:
    return {"status": "ok", "backend": settings.ton_signer_backend}


@app.post("/internal/v1/sign-and-broadcast", response_model=SignerResponse)
async def sign_and_broadcast(
    request: Request,
    x_signer_timestamp: str | None = Header(default=None),
    x_signer_nonce: str | None = Header(default=None),
    x_signer_signature: str | None = Header(default=None),
) -> SignerResponse:
    body = await request.body()
    if not x_signer_timestamp or not x_signer_nonce or not x_signer_signature:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing signer authentication")
    try:
        timestamp = int(x_signer_timestamp)
    except ValueError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signer timestamp") from exc
    if abs(int(time.time()) - timestamp) > settings.ton_signer_max_clock_skew_seconds:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Signer timestamp is outside allowed skew")
    if not verify_signer_signature(
        settings.ton_signer_shared_secret,
        x_signer_timestamp,
        x_signer_nonce,
        body,
        x_signer_signature,
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signer signature")
    if not await _accept_nonce(x_signer_nonce, timestamp):
        raise HTTPException(status.HTTP_409_CONFLICT, "Signer nonce was already used")
    try:
        payload = SignerRequest.model_validate_json(body)
    except ValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, exc.errors()) from exc

    cached = _idempotency_results.get(payload.idempotency_key)
    if cached is not None:
        return cached
    _validate_policy(payload)

    backend = settings.ton_signer_backend.lower()
    if (
        backend == "real"
        and settings.ton_destination_policy.lower() == "dynamic"
        and not settings.ton_dynamic_real_signing_allowed
    ):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Dynamic-destination real signing requires explicit operator enablement",
        )
    if (
        settings.is_production
        and backend == "mock"
        and not settings.allow_mock_ton_signer_in_production
    ):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Mock signer is disabled in production",
        )
    if backend == "real":
        from signer.real_backend import RealSignerError, sign_and_broadcast_real
        try:
            result = await sign_and_broadcast_real(payload)
        except RealSignerError as exc:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
        _idempotency_results[payload.idempotency_key] = result
        return result
    if backend != "mock":
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Unsupported signer backend")
    digest = hashlib.sha256(
        f"{payload.idempotency_key}:{payload.wallet_code}:{payload.payload_hash}".encode()
    ).hexdigest()
    result = SignerResponse(
        external_message_hash=f"remote_mock_{digest}",
        seqno=None,
        broadcasted=False,
        signer_mode="remote_mock",
        raw_result={
            "mode": "remote_mock",
            "broadcast": False,
            "request_id": payload.request_id,
        },
    )
    _idempotency_results[payload.idempotency_key] = result
    while len(_idempotency_results) > _MAX_CACHE:
        _idempotency_results.popitem(last=False)
    return result
