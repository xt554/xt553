from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass
from typing import Any

from services.ton_address import normalize_ton_address


class FragmentCaptureError(ValueError):
    pass


@dataclass(frozen=True)
class FragmentPaymentRequest:
    destination: str
    amount_nano: int
    payload_boc: str
    valid_until: int
    network: str = "-239"
    source_address: str | None = None
    state_init: str | None = None
    extra_currency: dict[str, str] | None = None
    expected_amount_nano: int | None = None

    @property
    def normalized_destination(self) -> str:
        return normalize_ton_address(self.destination)

    @property
    def normalized_source(self) -> str | None:
        return normalize_ton_address(self.source_address) if self.source_address else None

    @property
    def payload_hash(self) -> str:
        try:
            raw = base64.b64decode(self.payload_boc, validate=True)
        except Exception:
            raw = self.payload_boc.encode()
        return hashlib.sha256(raw).hexdigest()

    @property
    def schema_hash(self) -> str:
        shape = {
            "network": self.network,
            "message_count": 1,
            "has_payload": bool(self.payload_boc),
            "has_state_init": bool(self.state_init),
            "extra_currency_keys": sorted((self.extra_currency or {}).keys()),
        }
        return hashlib.sha256(json.dumps(shape, sort_keys=True).encode()).hexdigest()

    @property
    def fingerprint(self) -> str:
        value = ":".join((self.network, self.normalized_source or "", self.normalized_destination,
                          str(self.amount_nano), self.payload_hash, str(self.valid_until)))
        return hashlib.sha256(value.encode()).hexdigest()

    @classmethod
    def from_tonconnect(cls, data: dict[str, Any], *, expected_amount_nano: int | None = None) -> "FragmentPaymentRequest":
        params = data.get("params", data)
        if not isinstance(params, dict):
            raise FragmentCaptureError("Invalid TON Connect request")
        if params.get("items") is not None:
            raise FragmentCaptureError("Structured TON Connect items are not supported")
        messages = params.get("messages") or []
        if len(messages) != 1:
            raise FragmentCaptureError("Expected exactly one TON transfer message")
        message = messages[0]
        if not isinstance(message, dict):
            raise FragmentCaptureError("Invalid TON transfer message")
        destination = str(message.get("address") or "").strip()
        payload_boc = str(message.get("payload") or "").strip()
        source_address = str(params.get("from") or "").strip() or None
        state_init = str(message.get("stateInit") or message.get("state_init") or "").strip() or None
        extra = message.get("extraCurrency") or message.get("extra_currency") or None
        if extra is not None and not isinstance(extra, dict):
            raise FragmentCaptureError("Invalid extraCurrency")
        try:
            amount_nano = int(message.get("amount"))
            valid_until = int(params.get("valid_until") or params.get("validUntil"))
        except (TypeError, ValueError) as exc:
            raise FragmentCaptureError("Invalid TON amount or valid_until") from exc
        if not destination or amount_nano <= 0 or valid_until <= 0:
            raise FragmentCaptureError("Invalid TON destination, amount or valid_until")
        try:
            normalize_ton_address(destination)
            if source_address:
                normalize_ton_address(source_address)
        except ValueError as exc:
            raise FragmentCaptureError(str(exc)) from exc
        return cls(destination=destination, amount_nano=amount_nano, payload_boc=payload_boc,
                   valid_until=valid_until, network=str(params.get("network") or "-239"),
                   source_address=source_address, state_init=state_init,
                   extra_currency={str(k): str(v) for k, v in (extra or {}).items()} or None,
                   expected_amount_nano=expected_amount_nano)
