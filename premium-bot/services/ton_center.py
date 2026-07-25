from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

import httpx

from core.config import settings
from services.ton_address import TonAddressError, normalize_ton_address


class TonCenterError(RuntimeError):
    pass


@dataclass(frozen=True)
class TonWalletState:
    balance_nano: int
    seqno: int
    status: str | None = None
    wallet_type: str | None = None


@dataclass(frozen=True)
class TonConfirmation:
    found: bool
    verified: bool
    tx_hash: str | None = None
    tx_lt: str | None = None
    aborted: bool = False
    reason: str | None = None
    raw: dict[str, Any] | None = None


def _headers() -> dict[str, str]:
    return {"X-API-Key": settings.toncenter_api_key} if settings.toncenter_api_key else {}


async def _get(url: str, *, params: dict[str, Any]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=settings.toncenter_timeout_seconds) as client:
            response = await client.get(url, params=params, headers=_headers())
    except httpx.HTTPError as exc:
        raise TonCenterError(f"TON Center request failed: {exc}") from exc
    if response.status_code >= 400:
        raise TonCenterError(f"TON Center HTTP {response.status_code}: {response.text[:300]}")
    try:
        data = response.json()
    except ValueError as exc:
        raise TonCenterError("TON Center returned invalid JSON") from exc
    if isinstance(data, dict) and data.get("ok") is False:
        raise TonCenterError(str(data.get("error") or "TON Center request failed"))
    return data


async def get_wallet_state(address: str) -> TonWalletState:
    url = f"{settings.toncenter_v3_url.rstrip('/')}/walletInformation"
    data = await _get(url, params={"address": address})
    result = data.get("result", data)
    try:
        return TonWalletState(
            balance_nano=int(result.get("balance") or 0),
            seqno=int(result.get("seqno") or 0),
            status=result.get("status"),
            wallet_type=result.get("wallet_type"),
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise TonCenterError("TON Center wallet information is malformed") from exc


def _transaction_aborted(tx: dict[str, Any]) -> bool:
    if bool(tx.get("aborted")):
        return True
    description = tx.get("description") or {}
    if isinstance(description, dict) and bool(description.get("aborted")):
        return True
    compute = description.get("compute_ph") if isinstance(description, dict) else None
    if isinstance(compute, dict) and compute.get("success") is False:
        return True
    return False


def _decode_body_sha256(message: dict[str, Any]) -> str | None:
    content = message.get("message_content") or {}
    body = content.get("body") if isinstance(content, dict) else None
    if not body or not isinstance(body, str):
        return None
    padded = body + "=" * ((4 - len(body) % 4) % 4)
    try:
        raw = base64.b64decode(padded, validate=True)
    except Exception:
        try:
            raw = base64.urlsafe_b64decode(padded)
        except Exception:
            return None
    import hashlib

    return hashlib.sha256(raw).hexdigest()


async def find_transaction_by_external_message(
    *,
    external_message_hash: str,
    wallet_address: str,
    destination_raw: str,
    amount_nano: int,
    payload_hash: str | None,
) -> TonConfirmation:
    url = f"{settings.toncenter_v3_url.rstrip('/')}/transactionsByMessage"
    data = await _get(
        url,
        params={"msg_hash": external_message_hash, "direction": "in", "limit": 10},
    )
    transactions = data.get("transactions") or []
    if not transactions:
        return TonConfirmation(found=False, verified=False, raw=data)

    expected_wallet = normalize_ton_address(wallet_address)
    expected_destination = destination_raw.lower()
    for tx in transactions:
        if not isinstance(tx, dict):
            continue
        account = tx.get("account")
        if account:
            try:
                if normalize_ton_address(str(account)) != expected_wallet:
                    continue
            except TonAddressError:
                continue
        aborted = _transaction_aborted(tx)
        matching_message: dict[str, Any] | None = None
        for message in tx.get("out_msgs") or []:
            if not isinstance(message, dict):
                continue
            destination = message.get("destination")
            try:
                destination_matches = (
                    destination is not None
                    and normalize_ton_address(str(destination)) == expected_destination
                )
            except TonAddressError:
                destination_matches = False
            try:
                amount_matches = int(message.get("value") or 0) == int(amount_nano)
            except (TypeError, ValueError):
                amount_matches = False
            if destination_matches and amount_matches:
                matching_message = message
                break
        if matching_message is None:
            return TonConfirmation(
                found=True,
                verified=False,
                tx_hash=str(tx.get("hash") or "") or None,
                tx_lt=str(tx.get("lt") or "") or None,
                aborted=aborted,
                reason="Confirmed wallet transaction does not contain the expected Fragment transfer",
                raw=tx,
            )
        if aborted:
            return TonConfirmation(
                found=True,
                verified=False,
                tx_hash=str(tx.get("hash") or "") or None,
                tx_lt=str(tx.get("lt") or "") or None,
                aborted=True,
                reason="TON wallet transaction was aborted",
                raw=tx,
            )
        observed_payload_hash = _decode_body_sha256(matching_message)
        if payload_hash and observed_payload_hash and observed_payload_hash != payload_hash:
            return TonConfirmation(
                found=True,
                verified=False,
                tx_hash=str(tx.get("hash") or "") or None,
                tx_lt=str(tx.get("lt") or "") or None,
                reason="Confirmed transfer payload does not match the captured Fragment payload",
                raw=tx,
            )
        return TonConfirmation(
            found=True,
            verified=True,
            tx_hash=str(tx.get("hash") or "") or None,
            tx_lt=str(tx.get("lt") or "") or None,
            aborted=False,
            raw=tx,
        )
    return TonConfirmation(
        found=True,
        verified=False,
        reason="External message was found but not on the expected hot wallet",
        raw=data,
    )
