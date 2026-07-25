from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import SystemSetting


async def setting_value(
    session: AsyncSession,
    key: str,
    default: Any,
) -> Any:
    setting = await session.get(SystemSetting, key)
    return default if setting is None else setting.value
