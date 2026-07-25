
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse
from sqlalchemy import func, or_, select

from api.deps import AdminUser, DbSession
from api.schemas import (
    FragmentAccountCreate,
    FragmentAccountOut,
    FragmentAccountUpdate,
    FragmentJobAdminOut,
    FragmentRunnerInstanceOut,
    FragmentRunnerSummary,
    Page,
)
from core.config import settings
from database.enums import FragmentAccountStatus, FragmentJobStatus, OrderStatus
from database.models import FragmentAccount, FragmentJob, FragmentRunnerInstance, Order
from services.audit import add_audit_log
from services.errors import ConflictError, NotFoundError, ValidationError

router = APIRouter(prefix="/fragment-runners")


def artifact_file(relative_path: str | None) -> Path:
    if not relative_path:
        raise NotFoundError("诊断文件不存在")
    root = Path(settings.fragment_runner_artifact_dir).resolve()
    target = (root / relative_path).resolve()
    if root not in target.parents or not target.is_file():
        raise NotFoundError("诊断文件不存在")
    return target


@router.get("/summary", response_model=FragmentRunnerSummary)
async def summary(session: DbSession, _: AdminUser) -> FragmentRunnerSummary:
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.fragment_runner_stale_seconds)
    online = await session.scalar(
        select(func.count(FragmentRunnerInstance.runner_id)).where(
            FragmentRunnerInstance.last_heartbeat_at >= cutoff
        )
    ) or 0
    stale = await session.scalar(
        select(func.count(FragmentRunnerInstance.runner_id)).where(
            FragmentRunnerInstance.last_heartbeat_at < cutoff
        )
    ) or 0
    async def account_count(status: str) -> int:
        return await session.scalar(select(func.count(FragmentAccount.id)).where(FragmentAccount.status == status)) or 0
    async def job_count(status: str) -> int:
        return await session.scalar(select(func.count(FragmentJob.id)).where(FragmentJob.status == status)) or 0
    return FragmentRunnerSummary(
        online_runners=online,
        stale_runners=stale,
        active_accounts=await account_count(FragmentAccountStatus.ACTIVE.value),
        login_required_accounts=await account_count(FragmentAccountStatus.LOGIN_REQUIRED.value),
        queued_jobs=await job_count(FragmentJobStatus.QUEUED.value),
        retry_wait_jobs=await job_count(FragmentJobStatus.RETRY_WAIT.value),
        manual_review_jobs=await job_count(FragmentJobStatus.MANUAL_REVIEW.value),
    )


@router.get("/instances", response_model=list[FragmentRunnerInstanceOut])
async def instances(session: DbSession, _: AdminUser):
    return list((await session.scalars(select(FragmentRunnerInstance).order_by(FragmentRunnerInstance.runner_id))).all())


@router.get("/accounts", response_model=list[FragmentAccountOut])
async def accounts(session: DbSession, _: AdminUser):
    return list((await session.scalars(select(FragmentAccount).order_by(FragmentAccount.priority, FragmentAccount.code))).all())


@router.post("/accounts", response_model=FragmentAccountOut)
async def create_account(payload: FragmentAccountCreate, session: DbSession, admin: AdminUser):
    account = FragmentAccount(**payload.model_dump(), status=FragmentAccountStatus.ACTIVE.value)
    session.add(account)
    await session.flush()
    add_audit_log(session, action="fragment_account.create", actor_id=admin.id, target_type="fragment_account", target_id=account.id, details=payload.model_dump())
    await session.commit()
    return account


@router.patch("/accounts/{account_id}", response_model=FragmentAccountOut)
async def update_account(account_id: str, payload: FragmentAccountUpdate, session: DbSession, admin: AdminUser):
    account = await session.get(FragmentAccount, account_id)
    if account is None:
        raise NotFoundError("Fragment 账号不存在")
    changes = payload.model_dump(exclude_unset=True)
    if "status" in changes:
        try:
            changes["status"] = FragmentAccountStatus(changes["status"].upper()).value
        except ValueError as exc:
            raise ValidationError("无效的 Fragment 账号状态") from exc
    for key, value in changes.items():
        setattr(account, key, value)
    add_audit_log(session, action="fragment_account.update", actor_id=admin.id, target_type="fragment_account", target_id=account.id, details=changes)
    await session.commit()
    return account


@router.post("/accounts/{account_id}/release", response_model=FragmentAccountOut)
async def release_account(account_id: str, session: DbSession, admin: AdminUser):
    account = await session.get(FragmentAccount, account_id)
    if account is None:
        raise NotFoundError("Fragment 账号不存在")
    account.lease_runner_id = None
    account.lease_job_id = None
    account.lease_expires_at = None
    add_audit_log(session, action="fragment_account.release", actor_id=admin.id, target_type="fragment_account", target_id=account.id)
    await session.commit()
    return account


def job_out(
    job: FragmentJob, order: Order | None, account: FragmentAccount | None
) -> FragmentJobAdminOut:
    data = FragmentJobAdminOut.model_validate(job).model_dump()
    data.update(
        order_no=order.order_no if order else None,
        target_username=order.target_username if order else None,
        account_code=account.code if account else None,
    )
    return FragmentJobAdminOut(**data)


@router.get("/jobs", response_model=Page)
async def jobs(
    session: DbSession,
    _: AdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    search: str | None = None,
):
    filters = []
    if status:
        filters.append(FragmentJob.status == status.upper())
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(or_(Order.order_no.like(pattern), Order.target_username.like(pattern), FragmentJob.runner_id.like(pattern)))
    total = await session.scalar(select(func.count(FragmentJob.id)).join(Order, Order.id == FragmentJob.order_id).where(*filters)) or 0
    rows = (await session.execute(
        select(FragmentJob, Order, FragmentAccount)
        .join(Order, Order.id == FragmentJob.order_id)
        .outerjoin(FragmentAccount, FragmentAccount.id == FragmentJob.account_id)
        .where(*filters)
        .order_by(FragmentJob.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )).all()
    return Page(items=[job_out(job, order, account) for job, order, account in rows], total=total, page=page, page_size=page_size)


@router.post("/jobs/{job_id}/retry", response_model=FragmentJobAdminOut)
async def retry_job(job_id: str, session: DbSession, admin: AdminUser):
    job = await session.get(FragmentJob, job_id)
    if job is None:
        raise NotFoundError("Fragment 任务不存在")
    order = await session.get(Order, job.order_id)
    if order is None or order.status != OrderStatus.WAIT_FRAGMENT.value:
        raise ConflictError("只有 WAIT_FRAGMENT 订单的任务可以重试")
    job.status = FragmentJobStatus.QUEUED.value
    job.runner_id = None
    job.lease_expires_at = None
    job.next_retry_at = None
    job.failure_kind = None
    job.finished_at = None
    job.last_error = None
    add_audit_log(session, action="fragment_job.retry", actor_id=admin.id, target_type="fragment_job", target_id=job.id)
    await session.commit()
    account = await session.get(FragmentAccount, job.account_id) if job.account_id else None
    return job_out(job, order, account)


@router.get("/jobs/{job_id}/artifacts/{kind}")
async def download_artifact(job_id: str, kind: str, session: DbSession, _: AdminUser):
    job = await session.get(FragmentJob, job_id)
    if job is None:
        raise NotFoundError("Fragment 任务不存在")
    paths = {
        "screenshot": job.screenshot_path,
        "trace": job.trace_path,
        "html": job.html_path,
        "console": job.console_path,
    }
    if kind not in paths:
        raise ValidationError("不支持的诊断文件类型")
    target = artifact_file(paths[kind])
    return FileResponse(target, filename=target.name)
