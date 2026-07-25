from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import TonTransactionStatus, WalletReservationStatus
from database.models import HotWallet, TonTransaction
from services.circuit_breaker import assert_closed, record_failure, record_success
from services.fragment_capture import FragmentPaymentRequest
from services.hot_wallet_router import release_wallet_reservation, reserve_hot_wallet
from services.ton_risk import ManualReviewRequired, validate_ton_payment
from services.ton_signer import SignRequest, SignResult, sign_and_broadcast


@dataclass(frozen=True)
class PreparedFragmentPayment:
    transaction_id: str
    wallet_code: str
    status: str
    external_message_hash: str | None = None
    broadcasted: bool = False
    signer_mode: str | None = None


async def prepare_fragment_payment(
    session: AsyncSession,
    *,
    order_id: str,
    captured: FragmentPaymentRequest,
) -> PreparedFragmentPayment:
    await assert_closed(session, "GLOBAL")
    await assert_closed(session, "FRAGMENT_PROVIDER")
    try:
        risk = await validate_ton_payment(session, captured=captured)
    except ManualReviewRequired as exc:
        existing = await session.scalar(select(TonTransaction).where(TonTransaction.order_id == order_id).with_for_update())
        if existing:
            return PreparedFragmentPayment(existing.id, "unassigned", existing.status)
        placeholder = await session.scalar(select(HotWallet).order_by(HotWallet.priority).limit(1))
        if placeholder is None:
            raise
        tx = TonTransaction(order_id=order_id, wallet_id=placeholder.id, request_id=f"review_{secrets.token_hex(10)}",
            idempotency_key=f"fragment:{order_id}:v3", valid_until=captured.valid_until,
            source_address=captured.normalized_source, destination=captured.normalized_destination,
            amount_nano=captured.amount_nano, payload_hash=captured.payload_hash,
            capture_fingerprint=captured.fingerprint, status=TonTransactionStatus.MANUAL_REVIEW.value,
            last_error=str(exc), raw_chain_result={"network": captured.network, "schema_hash": captured.schema_hash, "source": "fragment_capture_v3"})
        session.add(tx); await session.flush()
        return PreparedFragmentPayment(tx.id, placeholder.wallet_code, tx.status)

    existing = await session.scalar(
        select(TonTransaction).where(TonTransaction.order_id == order_id).with_for_update()
    )
    if existing and existing.status == TonTransactionStatus.MANUAL_REVIEW.value:
        # The browser resubmits the same plaintext request after an administrator
        # approves its schema. The old review row contains no secret material and
        # can be replaced by the real idempotent signing attempt.
        await session.delete(existing)
        await session.flush()
        existing = None
    if existing:
        wallet = await session.get(HotWallet, existing.wallet_id)
        return PreparedFragmentPayment(
            transaction_id=existing.id,
            wallet_code=wallet.wallet_code if wallet else "unknown",
            status=existing.status,
            external_message_hash=existing.external_message_hash,
            broadcasted=existing.status
            in {TonTransactionStatus.BROADCASTED.value, TonTransactionStatus.CONFIRMED.value},
            signer_mode=existing.signer_mode,
        )

    reservation = await reserve_hot_wallet(
        session,
        order_id=order_id,
        amount_nano=captured.amount_nano,
        source_address=captured.normalized_source,
    )
    wallet = await session.scalar(
        select(HotWallet).where(HotWallet.id == reservation.wallet_id).with_for_update()
    )
    if wallet is None:
        raise RuntimeError("Reserved hot wallet does not exist")
    try:
        await assert_closed(session, f"WALLET:{wallet.wallet_code}")
    except Exception:
        await release_wallet_reservation(session, reservation)
        raise

    request_id = f"frag_{secrets.token_hex(12)}"
    tx = TonTransaction(
        order_id=order_id,
        wallet_id=wallet.id,
        request_id=request_id,
        idempotency_key=f"fragment:{order_id}:v3",
        valid_until=captured.valid_until,
        source_address=captured.normalized_source,
        destination=captured.normalized_destination,
        amount_nano=captured.amount_nano,
        payload_hash=captured.payload_hash,
        capture_fingerprint=captured.fingerprint,
        signer_request_id=request_id,
        status=TonTransactionStatus.CREATED.value,
        raw_chain_result={
            "network": captured.network,
            "source": "fragment_capture_v3",
            "schema_hash": captured.schema_hash,
        },
    )
    session.add(tx)
    await session.flush()

    tx.status = TonTransactionStatus.SIGNING.value
    tx.attempt_count += 1
    try:
        result: SignResult = await sign_and_broadcast(
            SignRequest(
                request_id=request_id,
                order_id=order_id,
                wallet_code=wallet.wallet_code,
                source_address=captured.normalized_source,
                destination=captured.normalized_destination,
                amount_nano=captured.amount_nano,
                payload_boc=captured.payload_boc,
                payload_hash=captured.payload_hash,
                valid_until=captured.valid_until,
                network=captured.network,
                idempotency_key=tx.idempotency_key,
                expected_amount_nano=captured.expected_amount_nano or captured.amount_nano,
                schema_hash=captured.schema_hash,
            )
        )
    except Exception as exc:
        tx.status = TonTransactionStatus.FAILED.value
        tx.last_error = str(exc)[:500]
        tx.raw_chain_result = {**(tx.raw_chain_result or {}), "error": str(exc)}
        wallet.consecutive_failure_count += 1
        await release_wallet_reservation(session, reservation)
        await record_failure(session, f"WALLET:{wallet.wallet_code}", str(exc))
        await record_failure(session, "FRAGMENT_PROVIDER", str(exc))
        raise

    tx.external_message_hash = result.external_message_hash
    tx.seqno = result.seqno
    tx.signer_mode = result.signer_mode
    tx.raw_chain_result = {**(tx.raw_chain_result or {}), **result.raw_result}
    wallet.consecutive_failure_count = 0

    if result.broadcasted:
        now = datetime.now(UTC)
        tx.status = TonTransactionStatus.BROADCASTED.value
        tx.broadcast_at = now
        reservation.status = WalletReservationStatus.CONSUMED.value
        wallet.reserved_nano = max(0, wallet.reserved_nano - reservation.reserved_nano)
        today = now.date()
        if wallet.spent_date != today:
            wallet.daily_spent_nano = 0
            wallet.spent_date = today
        wallet.daily_spent_nano += captured.amount_nano
    else:
        tx.status = TonTransactionStatus.SIMULATED.value
        await release_wallet_reservation(session, reservation)

    await record_success(session, f"WALLET:{wallet.wallet_code}")
    await record_success(session, "FRAGMENT_PROVIDER")
    return PreparedFragmentPayment(
        transaction_id=tx.id,
        wallet_code=wallet.wallet_code,
        status=tx.status,
        external_message_hash=tx.external_message_hash,
        broadcasted=result.broadcasted,
        signer_mode=result.signer_mode,
    )
