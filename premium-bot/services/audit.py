from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AuditLog


def add_audit_log(
    session: AsyncSession,
    *,
    action: str,
    actor_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    session.add(
        AuditLog(
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details,
            ip_address=ip_address,
        )
    )
