from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Query
from sqlalchemy import func, or_, select

from api.deps import AdminUser, DbSession
from api.schemas import (
    DepositOrderAdminOut,
    DepositOrderOut,
    Page,
    WalletAccountAdminOut,
    WalletAdjustment,
    WalletLedgerEntryOut,
)
from database.enums import WalletEntryType
from database.models import (
    DepositOrder,
    User,
    UserWallet,
    WalletLedgerEntry,
)
from services.audit import add_audit_log
from services.errors import NotFoundError
from services.wallets import money, post_wallet_entry

router = APIRouter(prefix="/wallet-accounts")


def wallet_admin_out(wallet: UserWallet, user: User) -> WalletAccountAdminOut:
    return WalletAccountAdminOut(
        id=wallet.id,
        user_id=wallet.user_id,
        currency=wallet.currency,
        available_balance=wallet.available_balance,
        total_deposited=wallet.total_deposited,
        total_spent=wallet.total_spent,
        created_at=wallet.created_at,
        updated_at=wallet.updated_at,
        telegram_id=user.telegram_id,
        telegram_username=user.telegram_username,
        username=user.username,
    )


def deposit_admin_out(
    deposit: DepositOrder,
    user: User,
) -> DepositOrderAdminOut:
    data = DepositOrderOut.model_validate(deposit).model_dump()
    return DepositOrderAdminOut(
        **data,
        telegram_id=user.telegram_id,
        telegram_username=user.telegram_username,
        username=user.username,
    )


@router.get("", response_model=Page)
async def list_wallet_accounts(
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
                User.telegram_username.like(pattern),
                User.username.like(pattern),
                User.email.like(pattern),
            )
        )
    total = (
        await session.scalar(
            select(func.count(UserWallet.id))
            .join(User, User.id == UserWallet.user_id)
            .where(*filters)
        )
        or 0
    )
    rows = (
        await session.execute(
            select(UserWallet, User)
            .join(User, User.id == UserWallet.user_id)
            .where(*filters)
            .order_by(UserWallet.updated_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return Page(
        items=[wallet_admin_out(wallet, user) for wallet, user in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/deposits", response_model=Page)
async def list_deposits(
    session: DbSession,
    _: AdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    search: str | None = None,
) -> Page:
    filters = []
    if status:
        filters.append(DepositOrder.status == status.upper())
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                DepositOrder.deposit_no.like(pattern),
                DepositOrder.tx_hash.like(pattern),
            )
        )
    total = await session.scalar(select(func.count(DepositOrder.id)).where(*filters)) or 0
    rows = (
        await session.execute(
            select(DepositOrder, User)
            .join(User, User.id == DepositOrder.user_id)
            .where(*filters)
            .order_by(DepositOrder.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()
    return Page(
        items=[deposit_admin_out(deposit, user) for deposit, user in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{wallet_id}/ledger",
    response_model=list[WalletLedgerEntryOut],
)
async def wallet_ledger(
    wallet_id: str,
    session: DbSession,
    _: AdminUser,
    limit: int = Query(100, ge=1, le=500),
) -> list[WalletLedgerEntry]:
    if await session.get(UserWallet, wallet_id) is None:
        raise NotFoundError("用户钱包不存在")
    return list(
        (
            await session.scalars(
                select(WalletLedgerEntry)
                .where(WalletLedgerEntry.wallet_id == wallet_id)
                .order_by(WalletLedgerEntry.created_at.desc())
                .limit(limit)
            )
        ).all()
    )


@router.post("/{wallet_id}/adjust", response_model=WalletAccountAdminOut)
async def adjust_wallet(
    wallet_id: str,
    payload: WalletAdjustment,
    session: DbSession,
    admin: AdminUser,
) -> WalletAccountAdminOut:
    wallet = await session.get(UserWallet, wallet_id)
    if wallet is None:
        raise NotFoundError("用户钱包不存在")
    user = await session.get(User, wallet.user_id)
    if user is None:
        raise NotFoundError("用户不存在")
    credit = payload.direction == "CREDIT"
    amount = money(payload.amount) * (1 if credit else -1)
    reference_id = uuid4().hex
    await post_wallet_entry(
        session,
        wallet_id=wallet.id,
        entry_type=(WalletEntryType.ADMIN_CREDIT if credit else WalletEntryType.ADMIN_DEBIT),
        amount=amount,
        reference_type="ADMIN_ADJUSTMENT",
        reference_id=reference_id,
        idempotency_key=f"admin-adjustment:{reference_id}",
        description=payload.reason,
    )
    add_audit_log(
        session,
        action="wallet.adjust",
        actor_id=admin.id,
        target_type="user_wallet",
        target_id=wallet.id,
        details={
            "direction": payload.direction,
            "amount": str(payload.amount),
            "reason": payload.reason,
        },
    )
    await session.commit()
    await session.refresh(wallet)
    return wallet_admin_out(wallet, user)
