from fastapi import APIRouter
from sqlalchemy import select

from api.deps import AdminUser, DbSession
from api.schemas import PlanCreate, PlanOut, PlanUpdate
from database.models import Plan
from services.audit import add_audit_log
from services.errors import NotFoundError

router = APIRouter(prefix="/plans")


@router.get("", response_model=list[PlanOut])
async def list_plans(session: DbSession, _: AdminUser) -> list[Plan]:
    return list((await session.scalars(select(Plan).order_by(Plan.sort_order, Plan.months))).all())


@router.post("", response_model=PlanOut)
async def create_plan(payload: PlanCreate, session: DbSession, admin: AdminUser) -> Plan:
    plan = Plan(**payload.model_dump())
    session.add(plan)
    await session.flush()
    add_audit_log(
        session,
        action="plan.create",
        actor_id=admin.id,
        target_type="plan",
        target_id=plan.id,
        details=payload.model_dump(mode="json"),
    )
    await session.commit()
    return plan


@router.patch("/{plan_id}", response_model=PlanOut)
async def update_plan(
    plan_id: str,
    payload: PlanUpdate,
    session: DbSession,
    admin: AdminUser,
) -> Plan:
    plan = await session.get(Plan, plan_id)
    if plan is None:
        raise NotFoundError("套餐不存在")
    changes = payload.model_dump(exclude_unset=True)
    for key, value in changes.items():
        setattr(plan, key, value)
    add_audit_log(
        session,
        action="plan.update",
        actor_id=admin.id,
        target_type="plan",
        target_id=plan.id,
        details=payload.model_dump(mode="json", exclude_unset=True),
    )
    await session.commit()
    return plan
