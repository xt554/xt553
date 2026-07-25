from __future__ import annotations

import base64
from time import time

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from core.config import settings
from database.base import Base
from database.enums import TonSchemaStatus
from database.models import TonSchemaPolicy
from services.fragment_capture import FragmentPaymentRequest
from services.ton_address import normalize_ton_address, parse_ton_address
from services.ton_risk import RiskRejected, validate_ton_payment

SOURCE = "UQDt7K7GNl48mpQtXKLzafD8Vv2gJtUPEvKDMp7Z0JkWtTWr"
DESTINATION = "UQCj4dYYpzdTro70lUlYmu0wFfenSksjg1lDUINcIXh2p0cd"
PAYLOAD = "te6cckEBAQEAAgAAAA=="


def _friendly(raw: str, flag: int) -> str:
    from services.ton_address import _crc16_ccitt

    parsed = parse_ton_address(raw)
    body = bytes([flag, parsed.workchain & 0xFF]) + parsed.account_id
    encoded = body + _crc16_ccitt(body).to_bytes(2, "big")
    return base64.urlsafe_b64encode(encoded).decode().rstrip("=")


def test_eq_uq_raw_normalize_to_same_account() -> None:
    raw = normalize_ton_address(SOURCE)
    eq = _friendly(raw, 0x11)
    uq = _friendly(raw, 0x51)
    assert normalize_ton_address(eq) == raw
    assert normalize_ton_address(uq) == raw


@pytest.mark.asyncio
async def test_dynamic_schema_requires_review_then_can_be_approved(monkeypatch) -> None:
    pytest.importorskip("aiosqlite")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(settings, "fragment_automation_enabled", True)
    monkeypatch.setattr(settings, "ton_destination_policy", "dynamic")
    monkeypatch.setattr(settings, "ton_new_schema_action", "manual_review")
    monkeypatch.setattr(settings, "ton_allowed_destination_workchains", "0")
    monkeypatch.setattr(settings, "fragment_capture_min_ttl_seconds", 1)
    monkeypatch.setattr(settings, "fragment_capture_max_ttl_seconds", 600)

    captured = FragmentPaymentRequest.from_tonconnect(
        {
            "validUntil": int(time()) + 120,
            "network": "-239",
            "from": SOURCE,
            "messages": [{"address": DESTINATION, "amount": "1000000000", "payload": PAYLOAD}],
        },
        expected_amount_nano=1_000_000_000,
    )
    async with factory() as session:
        decision = await validate_ton_payment(session, captured=captured)
        assert decision.requires_manual_review
        schema = await session.scalar(select(TonSchemaPolicy))
        assert schema is not None
        schema.status = TonSchemaStatus.APPROVED.value
        await session.commit()

        decision = await validate_ton_payment(session, captured=captured)
        assert not decision.requires_manual_review

    await engine.dispose()


@pytest.mark.asyncio
async def test_quote_deviation_is_rejected(monkeypatch) -> None:
    pytest.importorskip("aiosqlite")
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(settings, "fragment_automation_enabled", True)
    monkeypatch.setattr(settings, "ton_amount_deviation_bps", 100)
    monkeypatch.setattr(settings, "ton_allowed_destination_workchains", "0")
    captured = FragmentPaymentRequest.from_tonconnect(
        {
            "validUntil": int(time()) + 120,
            "network": "-239",
            "from": SOURCE,
            "messages": [{"address": DESTINATION, "amount": "1020000000", "payload": PAYLOAD}],
        },
        expected_amount_nano=1_000_000_000,
    )
    async with factory() as session:
        with pytest.raises(RiskRejected):
            await validate_ton_payment(session, captured=captured)
    await engine.dispose()
