from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from database.enums import HotWalletStatus, TonTransactionStatus
from database.models import HotWallet, TonTransaction
from services.circuit_breaker import record_failure, record_success
from services.ton_center import (
    TonCenterError,
    find_transaction_by_external_message,
    get_wallet_state,
)


async def reconcile_ton_transactions(session: AsyncSession) -> dict[str, int]:
    transactions = list(
        (
            await session.scalars(
                select(TonTransaction)
                .where(TonTransaction.status == TonTransactionStatus.BROADCASTED.value)
                .order_by(TonTransaction.broadcast_at.asc())
                .limit(settings.ton_reconcile_batch_size)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    result = {"checked": 0, "confirmed": 0, "manual_review": 0, "pending": 0, "errors": 0}
    now = datetime.now(UTC)
    for tx in transactions:
        result["checked"] += 1
        wallet = await session.get(HotWallet, tx.wallet_id)
        if wallet is None or not tx.external_message_hash:
            tx.status = TonTransactionStatus.MANUAL_REVIEW.value
            tx.last_error = "Missing wallet metadata or external message hash"
            result["manual_review"] += 1
            continue
        try:
            confirmation = await find_transaction_by_external_message(
                external_message_hash=tx.external_message_hash,
                wallet_address=wallet.address,
                destination_raw=tx.destination_raw or tx.destination,
                amount_nano=tx.amount_nano,
                payload_hash=tx.payload_hash,
            )
        except TonCenterError as exc:
            tx.last_error = str(exc)[:500]
            result["errors"] += 1
            continue

        if confirmation.found and confirmation.verified:
            tx.status = TonTransactionStatus.CONFIRMED.value
            tx.tx_hash = confirmation.tx_hash
            tx.tx_lt = confirmation.tx_lt
            tx.confirmed_at = now
            tx.last_error = None
            tx.raw_chain_result = {
                **(tx.raw_chain_result or {}),
                "confirmation": confirmation.raw or {},
            }
            try:
                wallet_state = await get_wallet_state(wallet.address)
                wallet.balance_nano = wallet_state.balance_nano
                wallet.last_seqno = wallet_state.seqno
            except TonCenterError:
                pass
            await record_success(session, f"WALLET:{wallet.wallet_code}")
            await record_success(session, "FRAGMENT_PROVIDER")
            result["confirmed"] += 1
            continue

        if confirmation.found and not confirmation.verified:
            tx.status = TonTransactionStatus.MANUAL_REVIEW.value
            tx.tx_hash = confirmation.tx_hash
            tx.tx_lt = confirmation.tx_lt
            tx.last_error = (confirmation.reason or "TON confirmation mismatch")[:500]
            tx.raw_chain_result = {
                **(tx.raw_chain_result or {}),
                "confirmation_mismatch": confirmation.raw or {},
            }
            await record_failure(session, f"WALLET:{wallet.wallet_code}", tx.last_error)
            await record_failure(session, "FRAGMENT_PROVIDER", tx.last_error)
            result["manual_review"] += 1
            continue

        age = (now - (tx.broadcast_at or tx.created_at)).total_seconds()
        if age >= settings.ton_confirmation_timeout_seconds:
            tx.status = TonTransactionStatus.MANUAL_REVIEW.value
            tx.last_error = "TON broadcast confirmation timed out; automatic rebroadcast is forbidden"
            await record_failure(session, f"WALLET:{wallet.wallet_code}", tx.last_error)
            result["manual_review"] += 1
        else:
            result["pending"] += 1
    return result


async def sync_ton_wallet_inventory(session: AsyncSession) -> dict[str, int]:
    wallets = list(
        (
            await session.scalars(
                select(HotWallet).where(
                    HotWallet.status.in_(
                        (
                            HotWalletStatus.ACTIVE.value,
                            HotWalletStatus.PAUSED.value,
                            HotWalletStatus.DRAINING.value,
                        )
                    )
                )
            )
        ).all()
    )
    result = {"checked": 0, "updated": 0, "errors": 0}
    for wallet in wallets:
        result["checked"] += 1
        try:
            state = await get_wallet_state(wallet.address)
        except TonCenterError as exc:
            wallet.consecutive_failure_count += 1
            await record_failure(session, f"WALLET:{wallet.wallet_code}", str(exc))
            result["errors"] += 1
            continue
        wallet.balance_nano = state.balance_nano
        wallet.last_seqno = state.seqno
        wallet.consecutive_failure_count = 0
        await record_success(session, f"WALLET:{wallet.wallet_code}")
        result["updated"] += 1
    return result
