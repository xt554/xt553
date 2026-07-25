from __future__ import annotations

import asyncio

from sqlalchemy import select

from core.config import settings
from core.security import hash_password
from database.enums import UserRole
from database.models import User
from database.session import session_scope


async def sync_admin_password() -> None:
    async with session_scope() as session:
        admin = await session.scalar(select(User).where(User.username == settings.admin_username))
        if admin is None:
            session.add(
                User(
                    username=settings.admin_username,
                    password_hash=hash_password(settings.admin_password),
                    role=UserRole.ADMIN.value,
                    is_active=True,
                )
            )
        else:
            admin.password_hash = hash_password(settings.admin_password)
            admin.is_active = True


if __name__ == "__main__":
    asyncio.run(sync_admin_password())
