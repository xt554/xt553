from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.enums import DepositStatus, OrderStatus, PaymentStatus
from database.models import DepositOrder, Order, PaymentTransaction, Wallet
from services.orders import transition_order
from services.wallets import credit_deposit


@dataclass(slots=True)
class ChainTransfer:
    network: str
    tx_hash: str
    to_address: str
    amount: Decimal
    confirmations: int
    log_index: int = 0
    block_number: int | None = None
    block_time: datetime | None = None
    from_address: str | None = None
    token_contract: str | None = None
    raw_data: dict[str, Any] | None = None


@dataclass(slots=True)
class IngestResult:
    transaction: PaymentTransaction
    matched_order_id: str | None = None
    matched_deposit_id: str | None = None
    newly_paid: bool = False
    newly_credited: bool = False


def _address_predicate(column: Any, network: str, address: str) -> Any:
    if network in {"BEP20", "ERC20"}:
        return func.lower(column) == address.lower()
    return column == address


async def ingest_transfer(
    session: AsyncSession,
    transfer: ChainTransfer,
) -> IngestResult:
    network = transfer.network.upper()
    transaction = await session.scalar(
        select(PaymentTransaction).where(
            PaymentTransaction.network == network,
            PaymentTransaction.tx_hash == transfer.tx_hash,
            PaymentTransaction.log_index == transfer.log_index,
        )
    )
    if transaction is None:
        safe_raw_data = transfer.raw_data or {
            "network": network,
            "tx_hash": transfer.tx_hash,
            "log_index": transfer.log_index,
            "block_number": transfer.block_number,
            "block_time": transfer.block_time.isoformat() if transfer.block_time else None,
            "from_address": transfer.from_address,
            "to_address": transfer.to_address,
            "token_contract": transfer.token_contract,
            "amount": str(transfer.amount),
            "confirmations": transfer.confirmations,
        }
        transaction = PaymentTransaction(
            network=network,
            tx_hash=transfer.tx_hash,
            log_index=transfer.log_index,
            block_number=transfer.block_number,
            block_time=transfer.block_time,
            from_address=transfer.from_address,
            to_address=transfer.to_address,
            token_contract=transfer.token_contract,
            amount=transfer.amount,
            confirmations=transfer.confirmations,
            status=PaymentStatus.DETECTED.value,
            raw_data=safe_raw_data,
        )
        session.add(transaction)
        await session.flush()
    else:
        transaction.confirmations = max(transaction.confirmations, transfer.confirmations)
        transaction.block_number = transfer.block_number or transaction.block_number
        transaction.raw_data = transfer.raw_data or transaction.raw_data
        if transaction.order_id:
            return IngestResult(
                transaction=transaction,
                matched_order_id=transaction.order_id,
            )
        if transaction.deposit_order_id:
            return IngestResult(
                transaction=transaction,
                matched_deposit_id=transaction.deposit_order_id,
            )

    wallet = await session.scalar(
        select(Wallet).where(
            Wallet.network == network,
            _address_predicate(Wallet.address, network, transfer.to_address),
            Wallet.is_enabled.is_(True),
        )
    )
    if wallet is None:
        transaction.status = PaymentStatus.UNMATCHED.value
        return IngestResult(transaction=transaction)

    if transaction.confirmations < wallet.min_confirmations:
        return IngestResult(transaction=transaction)

    transaction.status = PaymentStatus.CONFIRMED.value
    late_payment_boundary = datetime.now(UTC) - timedelta(hours=24)
    deposit = await session.scalar(
        select(DepositOrder)
        .where(
            DepositOrder.network == network,
            _address_predicate(
                DepositOrder.payment_address,
                network,
                transfer.to_address,
            ),
            DepositOrder.payment_amount == transfer.amount,
            or_(
                DepositOrder.status == DepositStatus.WAIT_PAY.value,
                DepositOrder.status == DepositStatus.TIMEOUT.value,
            ),
            DepositOrder.created_at >= late_payment_boundary,
        )
        .order_by(DepositOrder.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if deposit is not None:
        transaction.deposit_order_id = deposit.id
        transaction.status = PaymentStatus.MATCHED.value
        await credit_deposit(session, deposit, tx_hash=transfer.tx_hash)
        return IngestResult(
            transaction=transaction,
            matched_deposit_id=deposit.id,
            newly_credited=True,
        )

    order = await session.scalar(
        select(Order)
        .where(
            Order.network == network,
            _address_predicate(Order.payment_address, network, transfer.to_address),
            Order.payment_amount == transfer.amount,
            or_(
                Order.status == OrderStatus.WAIT_PAY.value,
                Order.status == OrderStatus.TIMEOUT.value,
            ),
            Order.created_at >= late_payment_boundary,
        )
        .order_by(Order.created_at)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if order is None:
        transaction.status = PaymentStatus.UNMATCHED.value
        return IngestResult(transaction=transaction)

    transaction.order_id = order.id
    transaction.status = PaymentStatus.MATCHED.value
    order.tx_hash = transfer.tx_hash
    await transition_order(
        session,
        order,
        OrderStatus.PAID,
        reason=f"Confirmed {network} transaction {transfer.tx_hash}",
        actor_type="PAYMENT_SCANNER",
    )
    return IngestResult(
        transaction=transaction,
        matched_order_id=order.id,
        newly_paid=True,
    )
