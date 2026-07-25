
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from database.enums import (
    FragmentAccountStatus,
    FragmentJobStatus,
    FragmentRunnerStatus,
    OrderStatus,
)
from database.models import FragmentAccount, FragmentJob, FragmentRunnerInstance, Order
from services.errors import ConflictError, NotFoundError
from services.orders import transition_order


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def retry_delay(attempt_count: int) -> int:
    exponent = max(0, attempt_count - 1)
    return min(
        settings.fragment_runner_retry_base_seconds * (2**exponent),
        settings.fragment_runner_retry_max_seconds,
    )


async def ensure_fragment_job(session: AsyncSession, order: Order) -> FragmentJob:
    job = await session.scalar(select(FragmentJob).where(FragmentJob.order_id == order.id))
    if job is None:
        job = FragmentJob(
            order_id=order.id,
            status=FragmentJobStatus.QUEUED.value,
            max_attempts=settings.fragment_runner_max_attempts,
        )
        session.add(job)
        await session.flush()
    elif job.status in {
        FragmentJobStatus.FAILED.value,
        FragmentJobStatus.CANCELLED.value,
        FragmentJobStatus.MANUAL_REVIEW.value,
        FragmentJobStatus.LOGIN_REQUIRED.value,
        FragmentJobStatus.SELECTOR_ERROR.value,
    }:
        job.status = FragmentJobStatus.QUEUED.value
        job.runner_id = None
        job.lease_expires_at = None
        job.next_retry_at = None
        job.failure_kind = None
        job.finished_at = None
        job.last_error = None
    return job


async def _available_account(
    session: AsyncSession, now: datetime, preferred_id: str | None = None
) -> FragmentAccount | None:
    filters = [
        FragmentAccount.is_enabled.is_(True),
        FragmentAccount.status == FragmentAccountStatus.ACTIVE.value,
        or_(FragmentAccount.lease_expires_at.is_(None), FragmentAccount.lease_expires_at < now),
    ]
    if preferred_id:
        filters.append(FragmentAccount.id == preferred_id)
    return await session.scalar(
        select(FragmentAccount)
        .where(*filters)
        .order_by(FragmentAccount.priority, FragmentAccount.last_success_at, FragmentAccount.created_at)
        .with_for_update(skip_locked=True)
    )


async def claim_fragment_job(session: AsyncSession, runner_id: str) -> FragmentJob | None:
    now = datetime.now(UTC)
    job = await session.scalar(
        select(FragmentJob)
        .where(
            or_(
                FragmentJob.status == FragmentJobStatus.QUEUED.value,
                and_(
                    FragmentJob.status == FragmentJobStatus.RETRY_WAIT.value,
                    FragmentJob.next_retry_at <= now,
                ),
                and_(
                    FragmentJob.status.in_(
                        [FragmentJobStatus.CLAIMED.value, FragmentJobStatus.WAIT_CAPTURE.value]
                    ),
                    FragmentJob.lease_expires_at < now,
                ),
            )
        )
        .order_by(FragmentJob.created_at)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None

    account = await _available_account(session, now, job.account_id)
    if account is None and job.account_id is not None:
        account = await _available_account(session, now)
    if account is None:
        return None

    lease_seconds = max(
        settings.fragment_runner_lease_seconds, settings.fragment_runner_account_lease_seconds
    )
    lease_until = now + timedelta(seconds=lease_seconds)
    job.account_id = account.id
    job.profile_name = account.profile_name
    job.status = FragmentJobStatus.CLAIMED.value
    job.runner_id = runner_id
    job.attempt_count += 1
    job.started_at = job.started_at or now
    job.lease_expires_at = lease_until
    job.next_retry_at = None
    job.retry_delay_seconds = None

    account.lease_runner_id = runner_id
    account.lease_job_id = job.id
    account.lease_expires_at = lease_until
    return job


async def require_runner_job(session: AsyncSession, job_id: str, runner_id: str) -> FragmentJob:
    job = await session.scalar(
        select(FragmentJob).where(FragmentJob.id == job_id).with_for_update()
    )
    if job is None:
        raise NotFoundError("Fragment 任务不存在")
    if job.runner_id != runner_id:
        raise ConflictError("Fragment 任务不属于当前 Runner")
    return job


async def heartbeat_job(session: AsyncSession, job: FragmentJob) -> None:
    now = datetime.now(UTC)
    if job.status == FragmentJobStatus.CLAIMED.value:
        job.status = FragmentJobStatus.WAIT_CAPTURE.value
    lease_seconds = max(
        settings.fragment_runner_lease_seconds, settings.fragment_runner_account_lease_seconds
    )
    lease_until = now + timedelta(seconds=lease_seconds)
    job.lease_expires_at = lease_until
    if job.account_id:
        account = await session.scalar(
            select(FragmentAccount)
            .where(FragmentAccount.id == job.account_id)
            .with_for_update()
        )
        if account and account.lease_job_id == job.id:
            account.lease_expires_at = lease_until


async def release_account(session: AsyncSession, job: FragmentJob) -> None:
    if not job.account_id:
        return
    account = await session.scalar(
        select(FragmentAccount).where(FragmentAccount.id == job.account_id).with_for_update()
    )
    if account and account.lease_job_id == job.id:
        account.lease_runner_id = None
        account.lease_job_id = None
        account.lease_expires_at = None


async def finish_captured_job(session: AsyncSession, job: FragmentJob, *, success: bool) -> None:
    now = datetime.now(UTC)
    job.finished_at = now
    job.lease_expires_at = None
    job.status = (
        FragmentJobStatus.COMPLETED.value if success else FragmentJobStatus.MANUAL_REVIEW.value
    )
    if job.account_id:
        account = await session.scalar(
            select(FragmentAccount).where(FragmentAccount.id == job.account_id).with_for_update()
        )
        if account:
            if success:
                account.last_success_at = now
                account.last_login_at = now
                account.cookie_updated_at = now
                account.selector_checked_at = now
                account.selector_status = "OK"
                account.last_error = None
                account.status = FragmentAccountStatus.ACTIVE.value
            await release_account(session, job)


async def mark_job_failed(
    session: AsyncSession,
    job: FragmentJob,
    error: str,
    *,
    manual: bool = False,
    retryable: bool = True,
    failure_kind: str = "RUNNER_ERROR",
    screenshot_path: str | None = None,
    trace_path: str | None = None,
    html_path: str | None = None,
    console_path: str | None = None,
    selector_snapshot: dict | None = None,
) -> None:
    now = datetime.now(UTC)
    job.last_error = error[:4000]
    job.failure_kind = failure_kind[:64]
    job.screenshot_path = screenshot_path or job.screenshot_path
    job.trace_path = trace_path or job.trace_path
    job.html_path = html_path or job.html_path
    job.console_path = console_path or job.console_path
    job.selector_snapshot = selector_snapshot or job.selector_snapshot
    job.lease_expires_at = None

    account = None
    if job.account_id:
        account = await session.scalar(
            select(FragmentAccount).where(FragmentAccount.id == job.account_id).with_for_update()
        )
        if account:
            account.last_failure_at = now
            account.last_error = error[:4000]
            account.last_page_url = job.page_url
            if selector_snapshot and selector_snapshot.get("ok"):
                account.last_login_at = now
                account.cookie_updated_at = now
                account.selector_checked_at = now
                account.selector_status = "OK"
            if failure_kind == "LOGIN_REQUIRED":
                account.status = FragmentAccountStatus.LOGIN_REQUIRED.value
            elif failure_kind == "SELECTOR_ERROR":
                account.last_login_at = now
                account.cookie_updated_at = now
                account.selector_checked_at = now
                account.selector_status = "FAILED"
                account.status = FragmentAccountStatus.ERROR.value

    order = await session.scalar(select(Order).where(Order.id == job.order_id).with_for_update())
    if manual or failure_kind in {"LOGIN_REQUIRED", "SELECTOR_ERROR"}:
        if failure_kind == "LOGIN_REQUIRED":
            job.status = FragmentJobStatus.LOGIN_REQUIRED.value
        elif failure_kind == "SELECTOR_ERROR":
            job.status = FragmentJobStatus.SELECTOR_ERROR.value
        else:
            job.status = FragmentJobStatus.MANUAL_REVIEW.value
        job.finished_at = now
        if order and order.status == OrderStatus.WAIT_FRAGMENT.value:
            await transition_order(
                session,
                order,
                OrderStatus.MANUAL_REVIEW,
                reason=error[:1000],
                actor_type="FRAGMENT_RUNNER",
                actor_id=job.runner_id,
            )
    elif retryable and job.attempt_count < job.max_attempts:
        delay = retry_delay(job.attempt_count)
        job.status = FragmentJobStatus.RETRY_WAIT.value
        job.retry_delay_seconds = delay
        job.next_retry_at = now + timedelta(seconds=delay)
        job.runner_id = None
        if order:
            order.last_fulfillment_error = error[:1000]
            order.next_retry_at = job.next_retry_at
    else:
        job.status = FragmentJobStatus.FAILED.value
        job.finished_at = now
        if order and order.status == OrderStatus.WAIT_FRAGMENT.value:
            await transition_order(
                session,
                order,
                OrderStatus.FAILED,
                reason=error[:1000],
                actor_type="FRAGMENT_RUNNER",
                actor_id=job.runner_id,
            )

    await release_account(session, job)


async def update_runner_instance(
    session: AsyncSession,
    *,
    runner_id: str,
    status: str,
    mode: str,
    version: str,
    browser_healthy: bool,
    api_healthy: bool,
    fragment_reachable: bool,
    login_status: str,
    selector_status: str,
    current_job_id: str | None,
    current_account_code: str | None,
    page_url: str | None,
    last_error: str | None,
    metadata: dict | None,
) -> FragmentRunnerInstance:
    now = datetime.now(UTC)
    instance = await session.get(FragmentRunnerInstance, runner_id)
    if instance is None:
        instance = FragmentRunnerInstance(runner_id=runner_id)
        session.add(instance)
    instance.status = status[:24]
    instance.mode = mode[:24]
    instance.version = version[:32]
    instance.browser_healthy = browser_healthy
    instance.api_healthy = api_healthy
    instance.fragment_reachable = fragment_reachable
    instance.login_status = login_status[:24]
    instance.selector_status = selector_status[:24]
    instance.current_job_id = current_job_id
    instance.current_account_code = current_account_code
    instance.page_url = page_url
    instance.last_heartbeat_at = now
    instance.runtime_metadata = metadata
    if current_job_id:
        instance.last_claim_at = now
    if last_error:
        instance.last_error = last_error[:4000]
        instance.last_error_at = now
    elif status in {FragmentRunnerStatus.IDLE.value, FragmentRunnerStatus.ONLINE.value}:
        instance.last_error = None
    instance.queue_depth = (
        await session.scalar(
            select(func.count(FragmentJob.id)).where(
                FragmentJob.status.in_(
                    [FragmentJobStatus.QUEUED.value, FragmentJobStatus.RETRY_WAIT.value]
                )
            )
        )
        or 0
    )
    return instance
