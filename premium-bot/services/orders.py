from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import insert, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from database.enums import OrderStatus, PaymentMethod, PaymentNetwork, can_transition
from database.models import (
    Order,
    OrderSequence,
    OrderStatusHistory,
    Plan,
    User,
)
from services.errors import ConflictError, NotFoundError, ValidationError
from services.settings import setting_value
from services.wallets import (
    allocate_payment_amount,
    debit_order_balance,
    refund_order_balance,
    select_receiving_wallet,
)

TELEGRAM_USERNAME = re.compile(r"^@[A-Za-z0-9_]{5,32}$")


def normalize_telegram_username(value: str) -> str:
    username = value.strip()
    if not username.startswith("@"):
        username = f"@{username}"
    if not TELEGRAM_USERNAME.fullmatch(username):
        raise ValidationError("Telegram 用户名格式不正确")
    return username


async def _next_order_number(session: AsyncSession) -> str:
    today = date.today()
    dialect_name = session.bind.dialect.name if session.bind is not None else ""
    if dialect_name == "mysql":
        statement = mysql_insert(OrderSequence).values(sequence_date=today, current_value=0)
        statement = statement.on_duplicate_key_update(current_value=OrderSequence.current_value)
        await session.execute(statement)
    else:
        existing = await session.get(OrderSequence, today)
        if existing is None:
            await session.execute(
                insert(OrderSequence).values(sequence_date=today, current_value=0)
            )
    sequence = await session.scalar(
        select(OrderSequence).where(OrderSequence.sequence_date == today).with_for_update()
    )
    if sequence is None:
        raise RuntimeError("Could not allocate order number")
    sequence.current_value += 1
    await session.flush()
    return f"NO{today:%Y%m%d}{sequence.current_value:04d}"


async def create_order(
    session: AsyncSession,
    *,
    user: User,
    plan_id: str,
    target_username: str,
    network: str | None,
    payment_method: str = PaymentMethod.ONCHAIN.value,
    callback_url: str | None = None,
) -> Order:
    if not user.is_active:
        raise ValidationError("用户已被禁用")
    plan = await session.scalar(select(Plan).where(Plan.id == plan_id, Plan.is_active.is_(True)))
    if plan is None:
        raise NotFoundError("套餐不存在或已下架")
    try:
        method = PaymentMethod(payment_method.upper())
    except ValueError as exc:
        raise ValidationError("不支持的支付方式") from exc
    target = normalize_telegram_username(target_username)
    expire_minutes = int(
        await setting_value(
            session,
            "order_expire_minutes",
            settings.order_expire_minutes,
        )
    )
    if not 1 <= expire_minutes <= 1440:
        raise ValidationError("系统订单有效期配置不正确")
    now = datetime.now(UTC)

    if method == PaymentMethod.WALLET_BALANCE:
        order = Order(
            order_no=await _next_order_number(session),
            user_id=user.id,
            plan_id=plan.id,
            wallet_id=None,
            target_username=target,
            status=OrderStatus.WAIT_PAY.value,
            payment_method=method.value,
            network="INTERNAL",
            currency=plan.currency,
            quoted_amount=plan.price,
            payment_amount=plan.price,
            payment_address="USER_WALLET",
            expires_at=now + timedelta(minutes=expire_minutes),
            callback_url=callback_url,
        )
        session.add(order)
        await session.flush()
        session.add(
            OrderStatusHistory(
                order_id=order.id,
                from_status=None,
                to_status=OrderStatus.WAIT_PAY.value,
                reason="Wallet balance order created",
                actor_type="USER",
                actor_id=user.id,
            )
        )
        await debit_order_balance(session, order)
        await transition_order(
            session,
            order,
            OrderStatus.PAID,
            reason="Paid with internal USDT wallet",
            actor_type="USER_WALLET",
            actor_id=user.id,
        )
        return order

    if not network:
        raise ValidationError("请选择支付网络")
    try:
        payment_network = PaymentNetwork(network.upper())
    except ValueError as exc:
        raise ValidationError("不支持的支付网络") from exc
    if payment_network.value not in settings.enabled_network_list:
        raise ValidationError(f"{payment_network.value} 当前未启用")

    wallet = await select_receiving_wallet(session, payment_network)
    payment_amount = await allocate_payment_amount(
        session,
        base_amount=Decimal(plan.price),
        receive_wallet_id=wallet.id,
        network=payment_network.value,
    )
    order = Order(
        order_no=await _next_order_number(session),
        user_id=user.id,
        plan_id=plan.id,
        wallet_id=wallet.id,
        target_username=target,
        status=OrderStatus.WAIT_PAY.value,
        payment_method=method.value,
        network=payment_network.value,
        currency=plan.currency,
        quoted_amount=plan.price,
        payment_amount=payment_amount,
        payment_address=wallet.address,
        expires_at=now + timedelta(minutes=expire_minutes),
        callback_url=callback_url,
    )
    session.add(order)
    await session.flush()
    session.add(
        OrderStatusHistory(
            order_id=order.id,
            from_status=None,
            to_status=OrderStatus.WAIT_PAY.value,
            reason="Order created",
            actor_type="USER",
            actor_id=user.id,
        )
    )
    return order


async def transition_order(
    session: AsyncSession,
    order: Order,
    target: OrderStatus,
    *,
    reason: str | None = None,
    actor_type: str = "SYSTEM",
    actor_id: str | None = None,
) -> Order:
    current = OrderStatus(order.status)
    if current == target:
        return order
    if not can_transition(current, target):
        raise ConflictError(f"订单不能从 {current.value} 转为 {target.value}")
    now = datetime.now(UTC)
    order.status = target.value
    order.version += 1
    if target == OrderStatus.PAID:
        order.paid_at = now
        order.completed_at = None
    elif target == OrderStatus.PROCESSING:
        order.processing_at = now
        order.completed_at = None
        order.failure_reason = None
        order.last_fulfillment_error = None
        order.next_retry_at = None
    elif target == OrderStatus.MANUAL_REVIEW:
        order.manual_review_at = now
        order.failure_reason = reason
        order.last_fulfillment_error = reason
        order.next_retry_at = None
    elif target in {
        OrderStatus.COMPLETED,
        OrderStatus.FAILED,
        OrderStatus.REFUNDED,
        OrderStatus.TIMEOUT,
    }:
        order.completed_at = now
    if target == OrderStatus.FAILED:
        order.failure_reason = reason
        order.last_fulfillment_error = reason
        order.next_retry_at = None
    session.add(
        OrderStatusHistory(
            order_id=order.id,
            from_status=current.value,
            to_status=target.value,
            reason=reason,
            actor_type=actor_type,
            actor_id=actor_id,
        )
    )
    await session.flush()
    return order


async def expire_waiting_orders(session: AsyncSession, batch_size: int = 500) -> list[str]:
    now = datetime.now(UTC)
    orders = (
        await session.scalars(
            select(Order)
            .where(
                Order.status == OrderStatus.WAIT_PAY.value,
                Order.expires_at <= now,
            )
            .order_by(Order.expires_at)
            .with_for_update(skip_locked=True)
            .limit(batch_size)
        )
    ).all()
    expired: list[str] = []
    for order in orders:
        await transition_order(
            session,
            order,
            OrderStatus.TIMEOUT,
            reason="Payment window expired",
        )
        expired.append(order.id)
    return expired


async def get_order_by_no(
    session: AsyncSession, order_no: str, *, user_id: str | None = None
) -> Order:
    statement = select(Order).where(Order.order_no == order_no)
    if user_id:
        statement = statement.where(Order.user_id == user_id)
    order = await session.scalar(statement)
    if order is None:
        raise NotFoundError("订单不存在")
    return order

async def list_user_orders(
    session: AsyncSession,
    *,
    user_id: str,
    limit: int = 10,
) -> list[Order]:
    """查询用户最近的订单。"""

    result = await session.scalars(
        select(Order)
        .where(Order.user_id == user_id)
        .order_by(Order.created_at.desc())
        .limit(limit)
    )

    return list(result.all())

async def fail_and_refund_order(
    session: AsyncSession,
    order: Order,
    *,
    reason: str,
    actor_type: str = "SYSTEM",
    actor_id: str | None = None,
) -> Order:
    """Fail an order and idempotently return an internal-wallet payment."""
    if order.status not in {OrderStatus.FAILED.value, OrderStatus.REFUNDED.value}:
        await transition_order(
            session,
            order,
            OrderStatus.FAILED,
            reason=reason,
            actor_type=actor_type,
            actor_id=actor_id,
        )
    refunded = await refund_order_balance(session, order)
    if refunded is not None and order.status == OrderStatus.FAILED.value:
        await transition_order(
            session,
            order,
            OrderStatus.REFUNDED,
            reason="Internal wallet payment refunded",
            actor_type="USER_WALLET",
            actor_id=order.user_id,
        )
    return order
