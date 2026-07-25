from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import func, select

from api.deps import AdminUser, DbSession
from api.schemas import DashboardStats
from database.enums import OrderStatus
from database.models import Order, User, UserWallet

router = APIRouter()


@router.get("/stats", response_model=DashboardStats)
async def dashboard_stats(session: DbSession, _: AdminUser) -> DashboardStats:
    today = datetime.now(UTC).date()
    total_users = await session.scalar(select(func.count(User.id))) or 0
    total_orders = await session.scalar(select(func.count(Order.id))) or 0
    today_orders = (
        await session.scalar(
            select(func.count(Order.id)).where(func.date(Order.created_at) == today)
        )
        or 0
    )
    revenue = await session.scalar(
        select(func.coalesce(func.sum(Order.quoted_amount), 0)).where(
            Order.status == OrderStatus.COMPLETED.value
        )
    ) or Decimal(0)
    wallet_liability = await session.scalar(
        select(func.coalesce(func.sum(UserWallet.available_balance), 0))
    ) or Decimal(0)
    rows = (
        await session.execute(select(Order.status, func.count(Order.id)).group_by(Order.status))
    ).all()
    counts = {status: count for status, count in rows}
    for status_value in OrderStatus:
        counts.setdefault(status_value.value, 0)
    return DashboardStats(
        total_users=total_users,
        total_orders=total_orders,
        today_orders=today_orders,
        paid_revenue=Decimal(revenue),
        wallet_liability=Decimal(wallet_liability),
        status_counts=counts,
    )
