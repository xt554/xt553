
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Header, Response
from sqlalchemy import select

from api.deps import DbSession
from api.schemas import (
    FragmentCaptureOut,
    FragmentRunnerCaptureIn,
    FragmentRunnerClaimIn,
    FragmentRunnerFailIn,
    FragmentRunnerHeartbeatIn,
    FragmentRunnerJobOut,
    FragmentRunnerStatusIn,
)
from core.config import settings
from database.enums import FragmentJobStatus, OrderStatus, TonTransactionStatus
from database.models import FragmentAccount, FragmentRunnerInstance, Order
from services.errors import ConflictError
from services.fragment_capture import FragmentPaymentRequest
from services.fragment_jobs import (
    claim_fragment_job,
    finish_captured_job,
    heartbeat_job,
    mark_job_failed,
    require_runner_job,
    update_runner_instance,
)
from services.fragment_orchestrator import prepare_fragment_payment
from services.orders import transition_order

router = APIRouter(prefix="/runner/fragment", tags=["fragment-runner"])


def auth(value: str | None) -> None:
    if not value or value != settings.fragment_runner_token:
        raise ConflictError("Fragment Runner authentication failed")


@router.post("/claim", response_model=FragmentRunnerJobOut | None)
async def claim(
    payload: FragmentRunnerClaimIn,
    session: DbSession,
    x_fragment_runner_token: str | None = Header(default=None),
):
    auth(x_fragment_runner_token)
    job = await claim_fragment_job(session, payload.runner_id)
    if job is None:
        return Response(status_code=204)
    order = await session.scalar(select(Order).where(Order.id == job.order_id))
    account = await session.get(FragmentAccount, job.account_id)
    if order is None or account is None:
        raise ConflictError("Fragment job references missing order or account")
    await session.commit()
    return FragmentRunnerJobOut(
        id=job.id,
        order_id=order.id,
        order_no=order.order_no,
        target_username=order.target_username,
        months=order.plan.months,
        wallet_code=job.wallet_code,
        account_code=account.code,
        account_display_name=account.display_name,
        profile_name=account.profile_name,
        status=job.status,
        attempt_count=job.attempt_count,
        max_attempts=job.max_attempts,
    )


@router.post("/status")
async def status(
    payload: FragmentRunnerStatusIn,
    session: DbSession,
    x_fragment_runner_token: str | None = Header(default=None),
):
    auth(x_fragment_runner_token)
    instance = await update_runner_instance(
        session,
        runner_id=payload.runner_id,
        status=payload.status,
        mode=payload.mode,
        version=payload.version,
        browser_healthy=payload.browser_healthy,
        api_healthy=payload.api_healthy,
        fragment_reachable=payload.fragment_reachable,
        login_status=payload.login_status,
        selector_status=payload.selector_status,
        current_job_id=payload.current_job_id,
        current_account_code=payload.current_account_code,
        page_url=payload.page_url,
        last_error=payload.last_error,
        metadata=payload.metadata,
    )
    await session.commit()
    return {"status": instance.status, "queue_depth": instance.queue_depth}


@router.post("/{job_id}/heartbeat")
async def heartbeat(
    job_id: str,
    payload: FragmentRunnerHeartbeatIn,
    session: DbSession,
    x_fragment_runner_token: str | None = Header(default=None),
):
    auth(x_fragment_runner_token)
    job = await require_runner_job(session, job_id, payload.runner_id)
    await heartbeat_job(session, job)
    if payload.page_url:
        job.page_url = payload.page_url
    await session.commit()
    return {"status": "ok"}


@router.post("/{job_id}/capture", response_model=FragmentCaptureOut)
async def capture(
    job_id: str,
    payload: FragmentRunnerCaptureIn,
    session: DbSession,
    x_fragment_runner_token: str | None = Header(default=None),
):
    auth(x_fragment_runner_token)
    job = await require_runner_job(session, job_id, payload.runner_id)
    order = await session.scalar(select(Order).where(Order.id == job.order_id).with_for_update())
    if order is None or order.status != OrderStatus.WAIT_FRAGMENT.value:
        raise ConflictError(f"订单状态不允许捕获：{order.status if order else 'NOT_FOUND'}")
    captured = FragmentPaymentRequest.from_tonconnect(
        payload.request, expected_amount_nano=payload.expected_amount_nano
    )
    job.captured_request = payload.request
    job.quoted_ton_nano = payload.expected_amount_nano
    job.captured_at = datetime.now(UTC)
    job.page_url = payload.page_url
    job.screenshot_path = payload.screenshot_path
    job.trace_path = payload.trace_path
    job.html_path = payload.html_path
    job.console_path = payload.console_path
    job.selector_snapshot = payload.selector_snapshot
    job.status = FragmentJobStatus.CAPTURED.value
    await transition_order(
        session,
        order,
        OrderStatus.WAIT_SIGN,
        reason="TON Connect request captured by Fragment Runner",
        actor_type="FRAGMENT_RUNNER",
        actor_id=payload.runner_id,
    )
    result = await prepare_fragment_payment(session, order_id=order.id, captured=captured)
    manual = result.status == TonTransactionStatus.MANUAL_REVIEW.value
    if manual:
        await transition_order(
            session,
            order,
            OrderStatus.MANUAL_REVIEW,
            reason="TON transaction schema requires administrator approval",
            actor_type="TON_RISK",
            actor_id=result.wallet_code,
        )
    elif result.status == TonTransactionStatus.BROADCASTED.value:
        await transition_order(
            session,
            order,
            OrderStatus.BROADCASTED,
            reason="TON transaction broadcasted",
            actor_type="TON_SIGNER",
            actor_id=result.wallet_code,
        )
    await finish_captured_job(session, job, success=not manual)
    instance = await session.get(FragmentRunnerInstance, payload.runner_id)
    if instance and not manual:
        instance.last_success_at = datetime.now(UTC)
        instance.last_error = None
    await session.commit()
    return FragmentCaptureOut(
        transaction_id=result.transaction_id,
        wallet_code=result.wallet_code,
        status=result.status,
        external_message_hash=result.external_message_hash,
        broadcasted=result.broadcasted,
        signer_mode=result.signer_mode,
    )


@router.post("/{job_id}/fail")
async def fail(
    job_id: str,
    payload: FragmentRunnerFailIn,
    session: DbSession,
    x_fragment_runner_token: str | None = Header(default=None),
):
    auth(x_fragment_runner_token)
    job = await require_runner_job(session, job_id, payload.runner_id)
    if payload.page_url:
        job.page_url = payload.page_url
    await mark_job_failed(
        session,
        job,
        payload.error,
        manual=payload.manual_review,
        retryable=payload.retryable,
        failure_kind=payload.failure_kind,
        screenshot_path=payload.screenshot_path,
        trace_path=payload.trace_path,
        html_path=payload.html_path,
        console_path=payload.console_path,
        selector_snapshot=payload.selector_snapshot,
    )
    status_value = job.status
    retry_at = job.next_retry_at
    await session.commit()
    return {"status": status_value, "next_retry_at": retry_at}
