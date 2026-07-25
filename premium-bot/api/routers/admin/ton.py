from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from api.deps import AdminUser, DbSession
from api.schemas import (
    CircuitBreakerOut,
    Page,
    TonHotWalletBalanceUpdate,
    TonHotWalletCreate,
    TonHotWalletOut,
    TonHotWalletUpdate,
    TonReservationOut,
    TonTransactionOut,
    TonSchemaOut,
    TonSchemaUpdate,
    TonWhitelistCreate,
    TonWhitelistOut,
    TonWhitelistUpdate,
)
from core.config import settings
from database.enums import HotWalletStatus, WalletReservationStatus
from database.models import (
    CircuitBreaker,
    HotWallet,
    PaymentWhitelist,
    TonTransaction,
    TonTransactionSchema,
    WalletReservation,
)
from services.audit import add_audit_log
from services.errors import ConflictError, NotFoundError, ValidationError
from services.hot_wallet_router import release_wallet_reservation

router = APIRouter(prefix="/ton")


@router.get("/wallets", response_model=list[TonHotWalletOut])
async def list_hot_wallets(session: DbSession, _: AdminUser) -> list[HotWallet]:
    return list(
        (
            await session.scalars(
                select(HotWallet).order_by(HotWallet.priority.asc(), HotWallet.wallet_code.asc())
            )
        ).all()
    )


@router.post("/wallets", response_model=TonHotWalletOut)
async def create_hot_wallet(
    payload: TonHotWalletCreate,
    session: DbSession,
    admin: AdminUser,
) -> HotWallet:
    count = await session.scalar(select(func.count(HotWallet.id))) or 0
    if count >= settings.ton_hot_wallet_count:
        raise ConflictError(f"最多只能配置 {settings.ton_hot_wallet_count} 个热钱包")
    wallet = HotWallet(**payload.model_dump(), status=HotWalletStatus.ACTIVE.value)
    session.add(wallet)
    await session.flush()
    session.add(CircuitBreaker(breaker_key=f"WALLET:{wallet.wallet_code}"))
    add_audit_log(
        session,
        action="ton.wallet.create",
        actor_id=admin.id,
        target_type="hot_wallet",
        target_id=wallet.id,
        details={"wallet_code": wallet.wallet_code, "address": wallet.address},
    )
    await session.commit()
    return wallet


@router.patch("/wallets/{wallet_id}", response_model=TonHotWalletOut)
async def update_hot_wallet(
    wallet_id: str,
    payload: TonHotWalletUpdate,
    session: DbSession,
    admin: AdminUser,
) -> HotWallet:
    wallet = await session.scalar(
        select(HotWallet).where(HotWallet.id == wallet_id).with_for_update()
    )
    if wallet is None:
        raise NotFoundError("TON 热钱包不存在")
    values = payload.model_dump(exclude_unset=True, exclude_none=True)
    if "status" in values:
        try:
            values["status"] = HotWalletStatus(str(values["status"]).upper()).value
        except ValueError as exc:
            raise ValidationError("无效的钱包状态") from exc
        wallet.disabled_at = (
            datetime.now(UTC) if values["status"] == HotWalletStatus.DISABLED.value else None
        )
    for key, value in values.items():
        setattr(wallet, key, value)
    add_audit_log(
        session,
        action="ton.wallet.update",
        actor_id=admin.id,
        target_type="hot_wallet",
        target_id=wallet.id,
        details=values,
    )
    await session.commit()
    return wallet


@router.post("/wallets/{wallet_id}/balance", response_model=TonHotWalletOut)
async def update_hot_wallet_balance(
    wallet_id: str,
    payload: TonHotWalletBalanceUpdate,
    session: DbSession,
    admin: AdminUser,
) -> HotWallet:
    wallet = await session.scalar(
        select(HotWallet).where(HotWallet.id == wallet_id).with_for_update()
    )
    if wallet is None:
        raise NotFoundError("TON 热钱包不存在")
    if payload.balance_nano < wallet.reserved_nano:
        raise ConflictError("余额不能小于当前预占金额")
    before = wallet.balance_nano
    wallet.balance_nano = payload.balance_nano
    if payload.last_seqno is not None:
        wallet.last_seqno = payload.last_seqno
    add_audit_log(
        session,
        action="ton.wallet.balance.sync",
        actor_id=admin.id,
        target_type="hot_wallet",
        target_id=wallet.id,
        details={
            "before_nano": before,
            "after_nano": payload.balance_nano,
            "last_seqno": payload.last_seqno,
            "reason": payload.reason,
        },
    )
    await session.commit()
    return wallet


@router.get("/whitelist", response_model=list[TonWhitelistOut])
async def list_whitelist(session: DbSession, _: AdminUser) -> list[PaymentWhitelist]:
    return list(
        (
            await session.scalars(
                select(PaymentWhitelist).order_by(PaymentWhitelist.created_at.desc())
            )
        ).all()
    )


@router.post("/whitelist", response_model=TonWhitelistOut)
async def create_whitelist(
    payload: TonWhitelistCreate,
    session: DbSession,
    admin: AdminUser,
) -> PaymentWhitelist:
    if payload.valid_from and payload.valid_until and payload.valid_until <= payload.valid_from:
        raise ValidationError("白名单结束时间必须晚于开始时间")
    row = PaymentWhitelist(**payload.model_dump())
    session.add(row)
    await session.flush()
    add_audit_log(
        session,
        action="ton.whitelist.create",
        actor_id=admin.id,
        target_type="payment_whitelist",
        target_id=row.id,
        details={"destination": row.destination, "label": row.label},
    )
    await session.commit()
    return row


@router.patch("/whitelist/{whitelist_id}", response_model=TonWhitelistOut)
async def update_whitelist(
    whitelist_id: str,
    payload: TonWhitelistUpdate,
    session: DbSession,
    admin: AdminUser,
) -> PaymentWhitelist:
    row = await session.get(PaymentWhitelist, whitelist_id)
    if row is None:
        raise NotFoundError("TON 收款地址白名单不存在")
    values = payload.model_dump(exclude_unset=True)
    for key, value in values.items():
        setattr(row, key, value)
    if row.valid_from and row.valid_until and row.valid_until <= row.valid_from:
        raise ValidationError("白名单结束时间必须晚于开始时间")
    add_audit_log(
        session,
        action="ton.whitelist.update",
        actor_id=admin.id,
        target_type="payment_whitelist",
        target_id=row.id,
        details=values,
    )
    await session.commit()
    return row


@router.get("/transactions", response_model=Page)
async def list_ton_transactions(
    session: DbSession,
    _: AdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
    wallet_id: str | None = None,
) -> Page:
    filters = []
    if status:
        filters.append(TonTransaction.status == status.upper())
    if wallet_id:
        filters.append(TonTransaction.wallet_id == wallet_id)
    total = await session.scalar(select(func.count(TonTransaction.id)).where(*filters)) or 0
    rows = list(
        (
            await session.scalars(
                select(TonTransaction)
                .where(*filters)
                .order_by(TonTransaction.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return Page(
        items=[TonTransactionOut.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/reservations", response_model=Page)
async def list_ton_reservations(
    session: DbSession,
    _: AdminUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: str | None = None,
) -> Page:
    filters = [WalletReservation.status == status.upper()] if status else []
    total = await session.scalar(select(func.count(WalletReservation.id)).where(*filters)) or 0
    rows = list(
        (
            await session.scalars(
                select(WalletReservation)
                .where(*filters)
                .order_by(WalletReservation.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    )
    return Page(
        items=[TonReservationOut.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/reservations/{reservation_id}/release", response_model=TonReservationOut)
async def release_reservation(
    reservation_id: str,
    session: DbSession,
    admin: AdminUser,
) -> WalletReservation:
    reservation = await session.scalar(
        select(WalletReservation)
        .where(WalletReservation.id == reservation_id)
        .with_for_update()
    )
    if reservation is None:
        raise NotFoundError("TON 预占记录不存在")
    if not await release_wallet_reservation(session, reservation):
        raise ConflictError(f"当前状态不能释放：{reservation.status}")
    add_audit_log(
        session,
        action="ton.reservation.release",
        actor_id=admin.id,
        target_type="wallet_reservation",
        target_id=reservation.id,
    )
    await session.commit()
    return reservation


@router.get("/breakers", response_model=list[CircuitBreakerOut])
async def list_breakers(session: DbSession, _: AdminUser) -> list[CircuitBreaker]:
    return list(
        (
            await session.scalars(
                select(CircuitBreaker).order_by(CircuitBreaker.breaker_key.asc())
            )
        ).all()
    )


@router.post("/breakers/{breaker_key}/reset", response_model=CircuitBreakerOut)
async def reset_breaker(
    breaker_key: str,
    session: DbSession,
    admin: AdminUser,
) -> CircuitBreaker:
    breaker = await session.scalar(
        select(CircuitBreaker)
        .where(CircuitBreaker.breaker_key == breaker_key)
        .with_for_update()
    )
    if breaker is None:
        breaker = CircuitBreaker(breaker_key=breaker_key)
        session.add(breaker)
    breaker.state = "CLOSED"
    breaker.failure_count = 0
    breaker.opened_at = None
    breaker.cooldown_until = None
    breaker.reason = None
    add_audit_log(
        session,
        action="ton.breaker.reset",
        actor_id=admin.id,
        target_type="circuit_breaker",
        target_id=breaker_key,
    )
    await session.commit()
    return breaker


@router.get("/schemas", response_model=list[TonSchemaOut])
async def list_ton_schemas(session: DbSession, _: AdminUser) -> list[TonTransactionSchema]:
    return list((await session.scalars(
        select(TonTransactionSchema).order_by(
            TonTransactionSchema.enabled.asc(), TonTransactionSchema.updated_at.desc()
        )
    )).all())


@router.patch("/schemas/{schema_hash}", response_model=TonSchemaOut)
async def update_ton_schema(
    schema_hash: str, payload: TonSchemaUpdate, session: DbSession, admin: AdminUser
) -> TonTransactionSchema:
    row = await session.scalar(
        select(TonTransactionSchema).where(
            TonTransactionSchema.schema_hash == schema_hash
        ).with_for_update()
    )
    if row is None:
        raise NotFoundError("TON 交易结构不存在")
    row.enabled = payload.enabled
    row.approved_by = admin.id if payload.enabled else None
    row.approved_at = datetime.now(UTC) if payload.enabled else None
    add_audit_log(session, action="ton.schema.update", actor_id=admin.id,
                  target_type="ton_transaction_schema", target_id=schema_hash,
                  details={"enabled": payload.enabled})
    await session.commit()
    return row
