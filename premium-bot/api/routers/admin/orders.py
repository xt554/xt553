from decimal import Decimal

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from api.deps import AdminUser, DbSession
from api.schemas import OrderDetail, OrderOut, Page, RefundOut, RefundRequest
from core.config import settings
from database.enums import OrderStatus, PaymentMethod, RefundStatus
from database.models import Order, Refund
from services.audit import add_audit_log
from services.errors import ConflictError, NotFoundError, ValidationError
from services.orders import transition_order
from services.wallets import debit_order_balance, refund_order_balance
from worker.tasks import execute_refund_task, fulfill_order

router = APIRouter(prefix="/orders")


@router.get("", response_model=Page)
async def list_orders(
    session: DbSession,
    _: AdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    network: str | None = None,
    search: str | None = None,
) -> Page:
    filters = []
    if status:
        filters.append(Order.status == status.upper())
    if network:
        filters.append(Order.network == network.upper())
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(or_(Order.order_no.like(pattern), Order.target_username.like(pattern)))
    total = await session.scalar(select(func.count(Order.id)).where(*filters)) or 0
    orders = (
        await session.scalars(
            select(Order)
            .where(*filters)
            .order_by(Order.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return Page(
        items=[OrderOut.model_validate(order) for order in orders],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{order_id}", response_model=OrderDetail)
async def order_detail(order_id: str, session: DbSession, _: AdminUser) -> Order:
    order = await session.get(Order, order_id)
    if order is None:
        raise NotFoundError("订单不存在")
    await session.refresh(order, attribute_names=["history", "payments"])
    return order


@router.post("/{order_id}/retry", response_model=OrderOut)
async def retry_order(order_id: str, session: DbSession, admin: AdminUser) -> Order:
    order = await session.get(Order, order_id)
    if order is None:
        raise NotFoundError("订单不存在")
    if order.status not in {OrderStatus.FAILED.value, OrderStatus.REFUNDED.value, OrderStatus.MANUAL_REVIEW.value}:
        raise ConflictError("只有 FAILED、REFUNDED 或 MANUAL_REVIEW 订单可以重试")
    if (
        order.payment_method == PaymentMethod.WALLET_BALANCE.value
        and order.balance_refunded_at is not None
    ):
        await debit_order_balance(session, order)
    await transition_order(
        session,
        order,
        OrderStatus.PROCESSING,
        reason="Administrator requested retry",
        actor_type="ADMIN",
        actor_id=admin.id,
    )
    add_audit_log(
        session,
        action="order.retry",
        actor_id=admin.id,
        target_type="order",
        target_id=order.id,
    )
    await session.commit()
    try:
        fulfill_order.delay(order.id)
    except Exception as exc:
        await refund_order_balance(session, order)
        await session.commit()
        raise ConflictError("处理队列暂时不可用，已退回本次钱包扣款") from exc
    return order


@router.post("/{order_id}/refunds", response_model=RefundOut)
async def request_refund(
    order_id: str,
    payload: RefundRequest,
    session: DbSession,
    admin: AdminUser,
) -> Refund:
    if not settings.refund_provider_url:
        raise ValidationError("退款服务尚未配置")
    order = await session.get(Order, order_id)
    if order is None:
        raise NotFoundError("订单不存在")
    if not order.paid_at:
        raise ConflictError("未付款订单不能退款")
    if order.payment_method == PaymentMethod.WALLET_BALANCE.value:
        raise ValidationError("余额支付订单请通过用户钱包调账处理退款")
    amount = payload.amount or Decimal(order.payment_amount)
    if amount > order.payment_amount:
        raise ConflictError("退款金额不能超过实付金额")
    refund = Refund(
        order_id=order.id,
        requested_by=admin.id,
        destination_address=payload.destination_address,
        network=order.network,
        amount=amount,
        status=RefundStatus.REQUESTED.value,
    )
    session.add(refund)
    await session.flush()
    add_audit_log(
        session,
        action="refund.request",
        actor_id=admin.id,
        target_type="refund",
        target_id=refund.id,
        details={"order_id": order.id, "amount": str(amount)},
    )
    await session.commit()
    execute_refund_task.delay(refund.id)
    return refund
