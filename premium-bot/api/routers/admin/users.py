from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from api.deps import AdminUser, DbSession
from api.schemas import Page, UserOut, UserUpdate
from database.models import User
from services.audit import add_audit_log
from services.errors import NotFoundError

router = APIRouter(prefix="/users")


@router.get("", response_model=Page)
async def list_users(
    session: DbSession,
    _: AdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = None,
) -> Page:
    filters = []
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                User.username.like(pattern),
                User.telegram_username.like(pattern),
                User.email.like(pattern),
            )
        )
    total = await session.scalar(select(func.count(User.id)).where(*filters)) or 0
    users = (
        await session.scalars(
            select(User)
            .where(*filters)
            .order_by(User.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return Page(
        items=[UserOut.model_validate(user) for user in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    session: DbSession,
    admin: AdminUser,
) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    user.is_active = payload.is_active
    add_audit_log(
        session,
        action="user.update",
        actor_id=admin.id,
        target_type="user",
        target_id=user.id,
        details=payload.model_dump(),
    )
    await session.commit()
    return user
