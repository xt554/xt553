from fastapi import APIRouter
from sqlalchemy import select

from api.deps import AdminUser, DbSession
from api.schemas import SettingOut, SettingUpdate
from database.models import SystemSetting
from services.audit import add_audit_log

router = APIRouter(prefix="/settings")


@router.get("", response_model=list[SettingOut])
async def list_settings(session: DbSession, _: AdminUser) -> list[SystemSetting]:
    return list((await session.scalars(select(SystemSetting).order_by(SystemSetting.key))).all())


@router.put("/{key}", response_model=SettingOut)
async def update_setting(
    key: str,
    payload: SettingUpdate,
    session: DbSession,
    admin: AdminUser,
) -> SystemSetting:
    setting = await session.get(SystemSetting, key)
    if setting is None:
        setting = SystemSetting(key=key, updated_by=admin.id, **payload.model_dump())
        session.add(setting)
    else:
        setting.value = payload.value
        setting.description = payload.description
        setting.is_public = payload.is_public
        setting.updated_by = admin.id
    add_audit_log(
        session,
        action="setting.update",
        actor_id=admin.id,
        target_type="setting",
        target_id=key,
        details={"is_public": payload.is_public},
    )
    await session.commit()
    return setting
