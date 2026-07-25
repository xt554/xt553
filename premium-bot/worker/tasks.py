from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from database.enums import OrderStatus, PaymentMethod
from database.models import Order
from database.session import dispose_engine, session_scope
from services.callbacks import deliver_order_callback
from services.fragment_jobs import ensure_fragment_job
from services.fragment_monitor import monitor_fragment_runners
from services.hot_wallet_router import expire_wallet_reservations
from services.ton_chain import reconcile_ton_transactions
from services.ton_wallet_sync import sync_hot_wallets
from services.orders import expire_waiting_orders, fail_and_refund_order, transition_order
from services.premium import get_premium_service
from services.refunds import execute_refund
from services.wallets import expire_deposit_orders
from worker.celery_app import celery_app
from worker.payment.scanner import scan_all_wallets

logger = logging.getLogger(__name__)


async def _with_dispose[T](coroutine: Coroutine[Any, Any, T]) -> T:
    try:
        return await coroutine
    finally:
        await dispose_engine()


def run_async[T](coroutine: Coroutine[Any, Any, T]) -> T:
    return asyncio.run(_with_dispose(coroutine))


async def _fulfill(order_id: str) -> str:
    provider = get_premium_service()
    async with session_scope() as session:
        order = await session.scalar(select(Order).where(Order.id == order_id).with_for_update())
        if order is None:
            return "NOT_FOUND"
        if order.status in {OrderStatus.COMPLETED.value, OrderStatus.SUCCESS.value}:
            return "COMPLETED"
        if order.status in {OrderStatus.REFUNDED.value, OrderStatus.TIMEOUT.value}:
            return f"SKIPPED:{order.status}"
        if order.status == OrderStatus.MANUAL_REVIEW.value:
            return "MANUAL_REVIEW"
        if order.status not in {
            OrderStatus.PAID.value,
            OrderStatus.FAILED.value,
            OrderStatus.PROCESSING.value,
            OrderStatus.WAIT_FRAGMENT.value,
        }:
            return f"SKIPPED:{order.status}"
        if order.status == OrderStatus.FAILED.value:
            if order.payment_method == PaymentMethod.WALLET_BALANCE.value and order.balance_refunded_at:
                return "SKIPPED:REFUNDED"
            await transition_order(session, order, OrderStatus.PROCESSING, reason="Fulfillment retry started", actor_type="WORKER")
        elif order.status == OrderStatus.PAID.value:
            await transition_order(session, order, OrderStatus.PROCESSING, reason="Fulfillment started", actor_type="WORKER")
        order.fulfillment_attempts += 1
        target_username = order.target_username
        months = order.plan.months
        reference = order.premium_reference

    try:
        if reference:
            result = await provider.query(reference)
        else:
            created = await provider.create_order(target_username, months)
            reference = created.reference
            async with session_scope() as session:
                order = await session.scalar(select(Order).where(Order.id == order_id).with_for_update())
                if order is None:
                    return "NOT_FOUND"
                order.premium_reference = reference
                if order.status == OrderStatus.PROCESSING.value:
                    await transition_order(session, order, OrderStatus.WAIT_FRAGMENT, reason="Premium request created; waiting for Fragment execution", actor_type="PREMIUM_PROVIDER")
            result = await provider.purchase(reference)

        normalized = result.status.upper()
        async with session_scope() as session:
            order = await session.scalar(select(Order).where(Order.id == order_id).with_for_update())
            if order is None:
                return "NOT_FOUND"
            if normalized in {"SUCCESS", "COMPLETED"}:
                if order.status in {OrderStatus.PROCESSING.value, OrderStatus.WAIT_FRAGMENT.value, OrderStatus.CONFIRMING.value, OrderStatus.MANUAL_REVIEW.value}:
                    await transition_order(session, order, OrderStatus.COMPLETED, reason=result.message or "Premium delivery verified", actor_type="PREMIUM_PROVIDER")
                return "COMPLETED"
            if normalized in {"FAILED", "CANCELLED"}:
                await fail_and_refund_order(session, order, reason=result.message or "Provider reported failure", actor_type="PREMIUM_PROVIDER")
                return order.status
            if order.status == OrderStatus.PROCESSING.value:
                await transition_order(session, order, OrderStatus.WAIT_FRAGMENT, reason=result.message or "Waiting for Fragment runner", actor_type="PREMIUM_PROVIDER")
            if order.status == OrderStatus.WAIT_FRAGMENT.value:
                await ensure_fragment_job(session, order)
            return "WAIT_FRAGMENT"
    except Exception as exc:
        async with session_scope() as session:
            order = await session.scalar(select(Order).where(Order.id == order_id).with_for_update())
            if order:
                order.last_fulfillment_error = str(exc)[:1000]
                order.next_retry_at = datetime.now(UTC) + timedelta(seconds=60)
        raise


@celery_app.task(
    bind=True,
    name="worker.tasks.fulfill_order",
    max_retries=8,
)
def fulfill_order(self: Any, order_id: str) -> str:
    try:
        result = run_async(_fulfill(order_id))
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            run_async(_mark_fulfillment_failed(order_id, str(exc)))
            deliver_callback.delay(order_id)
            return "FAILED"
        countdown = min(2 ** (self.request.retries + 1), 300)
        raise self.retry(exc=exc, countdown=countdown) from exc
    else:
        deliver_callback.delay(order_id)
        return result


async def _mark_fulfillment_failed(order_id: str, reason: str) -> None:
    async with session_scope() as session:
        order = await session.scalar(select(Order).where(Order.id == order_id).with_for_update())
        if order and order.status in {
            OrderStatus.PROCESSING.value,
            OrderStatus.WAIT_FRAGMENT.value,
            OrderStatus.WAIT_SIGN.value,
            OrderStatus.BROADCASTED.value,
            OrderStatus.CONFIRMING.value,
        }:
            await fail_and_refund_order(
                session,
                order,
                reason=f"Retries exhausted: {reason[:900]}",
                actor_type="WORKER",
            )


@celery_app.task(name="worker.tasks.expire_orders")
def expire_orders() -> int:
    async def work() -> list[str]:
        async with session_scope() as session:
            return await expire_waiting_orders(session)

    ids = run_async(work())
    for order_id in ids:
        deliver_callback.delay(order_id)
    return len(ids)


@celery_app.task(name="worker.tasks.expire_deposits")
def expire_deposits() -> int:
    async def work() -> list[str]:
        async with session_scope() as session:
            return await expire_deposit_orders(session)

    return len(run_async(work()))


@celery_app.task(name="worker.tasks.expire_ton_reservations")
def expire_ton_reservations() -> int:
    async def work() -> int:
        async with session_scope() as session:
            return await expire_wallet_reservations(session)

    return run_async(work())


@celery_app.task(name="worker.tasks.scan_payments")
def scan_payments() -> int:
    paid_ids = run_async(scan_all_wallets())
    for order_id in paid_ids:
        fulfill_order.delay(order_id)
        deliver_callback.delay(order_id)
    return len(paid_ids)


@celery_app.task(name="worker.tasks.poll_processing_orders")
def poll_processing_orders() -> int:
    async def work() -> list[str]:
        stale = datetime.now(UTC) - timedelta(seconds=45)
        async with session_scope() as session:
            return list(
                (
                    await session.scalars(
                        select(Order.id).where(
                            Order.status.in_([OrderStatus.PROCESSING.value, OrderStatus.WAIT_FRAGMENT.value]),
                            Order.updated_at <= stale,
                        )
                    )
                ).all()
            )

    order_ids = run_async(work())
    for order_id in order_ids:
        fulfill_order.delay(order_id)
    return len(order_ids)


@celery_app.task(
    bind=True,
    name="worker.tasks.deliver_callback",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 6},
)
def deliver_callback(self: Any, order_id: str) -> bool:
    delivered = run_async(deliver_order_callback(order_id, self.request.retries + 1))
    if not delivered:
        raise RuntimeError("Order callback was not accepted")
    return True


@celery_app.task(
    name="worker.tasks.execute_refund",
)
def execute_refund_task(refund_id: str) -> None:
    run_async(execute_refund(refund_id))


@celery_app.task(name="worker.tasks.reconcile_ton_transactions")
def reconcile_ton_transactions_task() -> int:
    async def work() -> int:
        async with session_scope() as session:
            return await reconcile_ton_transactions(session)
    return run_async(work())


@celery_app.task(name="worker.tasks.sync_ton_wallets")
def sync_ton_wallets_task() -> int:
    async def work() -> int:
        async with session_scope() as session:
            return await sync_hot_wallets(session)
    return run_async(work())


@celery_app.task(name="worker.tasks.monitor_fragment_runners")
def monitor_fragment_runner_health() -> int:
    async def _run() -> int:
        async with session_scope() as session:
            return await monitor_fragment_runners(session)

    return run_async(_run())
