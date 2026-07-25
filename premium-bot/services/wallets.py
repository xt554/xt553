from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from database.enums import (
    DepositStatus,
    OrderStatus,
    PaymentMethod,
    PaymentNetwork,
    WalletEntryType,
)
from database.models import (
    DepositOrder,
    Order,
    User,
    UserWallet,
    Wallet,
    WalletLedgerEntry,
)
from services.errors import ConflictError, NotFoundError, ValidationError

MONEY_SCALE = Decimal("0.000001")


def money(value: Decimal | str | int) -> Decimal:
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValidationError("金额格式不正确") from exc
    if not amount.is_finite():
        raise ValidationError("金额格式不正确")
    return amount.quantize(MONEY_SCALE)


async def ensure_user_wallet(
    session: AsyncSession,
    user_id: str,
    *,
    for_update: bool = False,
) -> UserWallet:
    statement = select(UserWallet).where(
        UserWallet.user_id == user_id,
        UserWallet.currency == "USDT",
    )
    if for_update:
        statement = statement.with_for_update()
    wallet = await session.scalar(statement)
    if wallet is None:
        wallet = UserWallet(user_id=user_id, currency="USDT")
        session.add(wallet)
        await session.flush()
    return wallet


async def select_receiving_wallet(
    session: AsyncSession,
    network: PaymentNetwork,
) -> Wallet:
    wallet = await session.scalar(
        select(Wallet)
        .where(Wallet.network == network.value, Wallet.is_enabled.is_(True))
        .order_by(
            Wallet.last_used_at.is_not(None),
            Wallet.last_used_at,
            Wallet.created_at,
        )
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if wallet is None:
        raise ValidationError(f"{network.value} 暂无可用收款钱包")
    wallet.last_used_at = datetime.now(UTC)
    return wallet


async def allocate_payment_amount(
    session: AsyncSession,
    *,
    base_amount: Decimal,
    receive_wallet_id: str,
    network: str,
    force_unique: bool = False,
) -> Decimal:
    base = money(base_amount)
    if not settings.payment_unique_amount and not force_unique:
        return base
    scale = max(2, min(settings.payment_amount_scale, 6))
    unit = Decimal(1).scaleb(-scale)
    max_suffix = 10**scale - 1
    for _ in range(50):
        suffix = Decimal(secrets.randbelow(max_suffix) + 1) * unit
        candidate = money((base + suffix).quantize(unit))
        order_count = await session.scalar(
            select(func.count(Order.id)).where(
                Order.wallet_id == receive_wallet_id,
                Order.network == network,
                Order.payment_amount == candidate,
                Order.status == OrderStatus.WAIT_PAY.value,
            )
        )
        deposit_count = await session.scalar(
            select(func.count(DepositOrder.id)).where(
                DepositOrder.receive_wallet_id == receive_wallet_id,
                DepositOrder.network == network,
                DepositOrder.payment_amount == candidate,
                DepositOrder.status == DepositStatus.WAIT_PAY.value,
            )
        )
        if not order_count and not deposit_count:
            return candidate
    raise ConflictError("暂时无法分配唯一付款金额，请稍后重试")


async def post_wallet_entry(
    session: AsyncSession,
    *,
    wallet_id: str,
    entry_type: WalletEntryType,
    amount: Decimal,
    reference_type: str,
    reference_id: str,
    idempotency_key: str,
    description: str | None = None,
) -> WalletLedgerEntry:
    existing = await session.scalar(
        select(WalletLedgerEntry).where(WalletLedgerEntry.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing

    wallet = await session.scalar(
        select(UserWallet).where(UserWallet.id == wallet_id).with_for_update()
    )
    if wallet is None:
        raise NotFoundError("用户钱包不存在")
    delta = money(amount)
    if delta == 0:
        raise ValidationError("钱包变动金额不能为零")
    new_balance = money(Decimal(wallet.available_balance) + delta)
    if new_balance < 0:
        raise ConflictError("钱包余额不足")

    wallet.available_balance = new_balance
    wallet.version += 1
    if entry_type == WalletEntryType.DEPOSIT:
        wallet.total_deposited = money(Decimal(wallet.total_deposited) + delta)
    elif entry_type == WalletEntryType.ORDER_PAYMENT:
        wallet.total_spent = money(Decimal(wallet.total_spent) + abs(delta))
    elif entry_type == WalletEntryType.ORDER_REFUND:
        wallet.total_spent = max(
            Decimal("0"),
            money(Decimal(wallet.total_spent) - abs(delta)),
        )

    entry = WalletLedgerEntry(
        wallet_id=wallet.id,
        entry_type=entry_type.value,
        amount=delta,
        balance_after=new_balance,
        reference_type=reference_type,
        reference_id=reference_id,
        idempotency_key=idempotency_key,
        description=description,
    )
    session.add(entry)
    await session.flush()
    return entry


async def create_deposit_order(
    session: AsyncSession,
    *,
    user: User,
    requested_amount: Decimal,
    network: str,
) -> DepositOrder:
    if not user.is_active:
        raise ValidationError("用户已被禁用")
    amount = money(requested_amount)
    minimum = money(settings.wallet_min_deposit)
    maximum = money(settings.wallet_max_deposit)
    if amount < minimum or amount > maximum:
        raise ValidationError(f"充值金额需在 {minimum}～{maximum} USDT 之间")
    try:
        payment_network = PaymentNetwork(network.upper())
    except ValueError as exc:
        raise ValidationError("不支持的充值网络") from exc
    if payment_network.value not in settings.enabled_network_list:
        raise ValidationError(f"{payment_network.value} 当前未启用")

    user_wallet = await ensure_user_wallet(session, user.id)
    receive_wallet = await select_receiving_wallet(session, payment_network)
    payment_amount = await allocate_payment_amount(
        session,
        base_amount=amount,
        receive_wallet_id=receive_wallet.id,
        network=payment_network.value,
        force_unique=True,
    )
    for _ in range(10):
        deposit_no = f"DP{datetime.now(UTC):%Y%m%d}{secrets.token_hex(4).upper()}"
        exists = await session.scalar(
            select(func.count(DepositOrder.id)).where(DepositOrder.deposit_no == deposit_no)
        )
        if not exists:
            break
    else:
        raise ConflictError("暂时无法生成充值单号，请稍后重试")

    deposit = DepositOrder(
        deposit_no=deposit_no,
        user_id=user.id,
        user_wallet_id=user_wallet.id,
        receive_wallet_id=receive_wallet.id,
        network=payment_network.value,
        requested_amount=amount,
        payment_amount=payment_amount,
        payment_address=receive_wallet.address,
        status=DepositStatus.WAIT_PAY.value,
        expires_at=datetime.now(UTC) + timedelta(minutes=settings.deposit_expire_minutes),
    )
    session.add(deposit)
    await session.flush()
    return deposit


async def credit_deposit(
    session: AsyncSession,
    deposit: DepositOrder,
    *,
    tx_hash: str,
) -> WalletLedgerEntry:
    if deposit.status == DepositStatus.CONFIRMED.value:
        existing = await session.scalar(
            select(WalletLedgerEntry).where(
                WalletLedgerEntry.idempotency_key == f"deposit:{deposit.id}:credit"
            )
        )
        if existing is None:
            raise RuntimeError("Confirmed deposit is missing its ledger entry")
        return existing
    if deposit.status not in {
        DepositStatus.WAIT_PAY.value,
        DepositStatus.TIMEOUT.value,
    }:
        raise ConflictError("充值单状态不可入账")
    entry = await post_wallet_entry(
        session,
        wallet_id=deposit.user_wallet_id,
        entry_type=WalletEntryType.DEPOSIT,
        amount=Decimal(deposit.payment_amount),
        reference_type="DEPOSIT",
        reference_id=deposit.id,
        idempotency_key=f"deposit:{deposit.id}:credit",
        description=f"{deposit.network} 链上充值",
    )
    deposit.status = DepositStatus.CONFIRMED.value
    deposit.tx_hash = tx_hash
    deposit.confirmed_at = datetime.now(UTC)
    return entry


async def debit_order_balance(
    session: AsyncSession,
    order: Order,
) -> WalletLedgerEntry:
    if order.payment_method != PaymentMethod.WALLET_BALANCE.value:
        raise ValidationError("该订单不是余额支付")
    user_wallet = await ensure_user_wallet(session, order.user_id, for_update=True)
    attempt = order.balance_payment_attempt + 1
    entry = await post_wallet_entry(
        session,
        wallet_id=user_wallet.id,
        entry_type=WalletEntryType.ORDER_PAYMENT,
        amount=-money(order.quoted_amount),
        reference_type="ORDER",
        reference_id=order.id,
        idempotency_key=f"order:{order.id}:payment:{attempt}",
        description=f"Premium 订单 {order.order_no}",
    )
    order.balance_payment_attempt = attempt
    order.balance_refunded_at = None
    return entry


async def refund_order_balance(
    session: AsyncSession,
    order: Order,
) -> WalletLedgerEntry | None:
    if (
        order.payment_method != PaymentMethod.WALLET_BALANCE.value
        or order.balance_payment_attempt < 1
        or order.balance_refunded_at is not None
    ):
        return None
    user_wallet = await ensure_user_wallet(session, order.user_id, for_update=True)
    entry = await post_wallet_entry(
        session,
        wallet_id=user_wallet.id,
        entry_type=WalletEntryType.ORDER_REFUND,
        amount=money(order.quoted_amount),
        reference_type="ORDER",
        reference_id=order.id,
        idempotency_key=(f"order:{order.id}:refund:{order.balance_payment_attempt}"),
        description=f"失败订单退款 {order.order_no}",
    )
    order.balance_refunded_at = datetime.now(UTC)
    return entry


async def expire_deposit_orders(
    session: AsyncSession,
    batch_size: int = 500,
) -> list[str]:
    now = datetime.now(UTC)
    deposits = (
        await session.scalars(
            select(DepositOrder)
            .where(
                DepositOrder.status == DepositStatus.WAIT_PAY.value,
                DepositOrder.expires_at <= now,
            )
            .order_by(DepositOrder.expires_at)
            .with_for_update(skip_locked=True)
            .limit(batch_size)
        )
    ).all()
    ids: list[str] = []
    for deposit in deposits:
        deposit.status = DepositStatus.TIMEOUT.value
        ids.append(deposit.id)
    return ids

async def list_user_deposits(
    session: AsyncSession,
    *,
    user_id: str,
    limit: int = 10,
) -> list[DepositOrder]:
    """查询用户最近的充值订单。"""

    result = await session.scalars(
        select(DepositOrder)
        .where(DepositOrder.user_id == user_id)
        .order_by(DepositOrder.created_at.desc())
        .limit(limit)
    )

    return list(result.all())