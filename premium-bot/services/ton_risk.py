from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from database.models import PaymentWhitelist, TonTransaction, TonTransactionSchema
from services.fragment_capture import FragmentPaymentRequest
from services.ton_units import ton_to_nano
from services.ton_address import normalize_ton_address


class RiskRejected(RuntimeError): pass
class ManualReviewRequired(RiskRejected): pass

@dataclass(frozen=True)
class RiskDecision:
    amount_nano: int
    destination: str
    network: str
    valid_until: int
    current_daily_spent_nano: int
    schema_hash: str

async def validate_ton_payment(session: AsyncSession, *, captured: FragmentPaymentRequest) -> RiskDecision:
    if not settings.fragment_automation_enabled:
        raise RiskRejected("Fragment automation is disabled")
    if settings.ton_require_mainnet and captured.network != "-239":
        raise RiskRejected("Only TON mainnet network -239 is allowed")
    if settings.ton_require_single_message is False:
        raise RiskRejected("Unsafe configuration: single-message enforcement must remain enabled")
    if captured.amount_nano <= 0 or captured.amount_nano > ton_to_nano(settings.ton_single_limit):
        raise RiskRejected("Payment amount is invalid or exceeds the single-order limit")
    if settings.ton_require_payload and not captured.payload_boc:
        raise RiskRejected("TON payload is required")
    if captured.state_init and not settings.ton_allow_state_init:
        raise RiskRejected("stateInit is not permitted")
    if captured.extra_currency and not settings.ton_allow_extra_currency:
        raise RiskRejected("extraCurrency is not permitted")
    now = datetime.now(UTC); ttl = captured.valid_until - int(now.timestamp())
    if ttl < settings.fragment_capture_min_ttl_seconds or ttl > settings.fragment_capture_max_ttl_seconds:
        raise RiskRejected("TON Connect request TTL is outside policy")
    if captured.expected_amount_nano is not None:
        expected = captured.expected_amount_nano
        deviation_bps = abs(captured.amount_nano - expected) * 10_000 // max(1, expected)
        if deviation_bps > settings.ton_amount_deviation_bps:
            raise RiskRejected("TON amount deviates from the trusted quote")
    elif settings.ton_amount_deviation_bps >= 0:
        raise ManualReviewRequired("Trusted expected TON amount is missing")

    policy = settings.ton_destination_policy.lower()
    if policy == "exact" or settings.ton_require_exact_destination:
        rows = list((await session.scalars(select(PaymentWhitelist).where(
            PaymentWhitelist.enabled.is_(True)))).all())
        whitelist = next((row for row in rows if normalize_ton_address(row.destination) == captured.normalized_destination), None)
        if whitelist is None:
            raise RiskRejected("Destination is not in the approved TON whitelist")
        if whitelist.maximum_single_nano and captured.amount_nano > whitelist.maximum_single_nano:
            raise RiskRejected("Payment exceeds destination-specific limit")
    elif policy != "dynamic":
        raise RiskRejected("Unsupported TON destination policy")

    schema = await session.scalar(select(TonTransactionSchema).where(
        TonTransactionSchema.schema_hash == captured.schema_hash).with_for_update())
    if schema is None:
        schema = TonTransactionSchema(schema_hash=captured.schema_hash, enabled=False,
            sample_count=1, first_destination=captured.normalized_destination,
            last_destination=captured.normalized_destination, last_payload_hash=captured.payload_hash)
        session.add(schema); await session.flush()
        if settings.ton_new_schema_action.lower() == "reject":
            raise RiskRejected("Unknown TON transaction schema")
        raise ManualReviewRequired("New TON transaction schema requires approval")
    schema.sample_count += 1; schema.last_destination = captured.normalized_destination
    schema.last_payload_hash = captured.payload_hash
    if not schema.enabled:
        raise ManualReviewRequired("TON transaction schema is awaiting approval")

    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    spent = await session.scalar(select(func.coalesce(func.sum(TonTransaction.amount_nano), 0)).where(
        TonTransaction.created_at >= start,
        TonTransaction.status.in_(("SIGNING", "BROADCASTED", "CONFIRMED"))))
    current_spent = int(spent or 0)
    if current_spent + captured.amount_nano > ton_to_nano(settings.ton_global_daily_limit):
        raise RiskRejected("Global daily TON limit would be exceeded")
    return RiskDecision(captured.amount_nano, captured.normalized_destination, captured.network,
                        captured.valid_until, current_spent, captured.schema_hash)
