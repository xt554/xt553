from fastapi import APIRouter, Query
from sqlalchemy import func, select

from api.deps import AdminUser, DbSession
from api.schemas import AuditLogOut, Page
from database.models import AuditLog

router = APIRouter(prefix="/logs")


@router.get("", response_model=Page)
async def list_logs(
    session: DbSession,
    _: AdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    action: str | None = None,
) -> Page:
    filters = [AuditLog.action.like(f"%{action}%")] if action else []
    total = await session.scalar(select(func.count(AuditLog.id)).where(*filters)) or 0
    logs = (
        await session.scalars(
            select(AuditLog)
            .where(*filters)
            .order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return Page(
        items=[AuditLogOut.model_validate(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
    )
