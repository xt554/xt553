from fastapi import APIRouter, Query
from sqlalchemy import select

from api.deps import DbSession, InternalAuth
from api.schemas import (
    DepositCreateInternal,
    DepositOrderOut,
    NetworkOut,
    OrderCreateInternal,
    OrderOut,
    PlanOut,
    TelegramUserUpsert,
    UserOut,
    UserWalletOut,
    WalletLedgerEntryOut,
    FragmentCaptureIn,
    FragmentCaptureOut,
)
from core.config import settings
from database.enums import OrderStatus
from database.models import (
    DepositOrder,
    Order,
    Plan,
    User,
    UserWallet,
    Wallet,
    WalletLedgerEntry,
)
from services.errors import ConflictError, NotFoundError
from services.fragment_capture import FragmentPaymentRequest
from services.fragment_orchestrator import prepare_fragment_payment
from services.orders import (
    create_order,
    fail_and_refund_order,
    get_order_by_no,
    list_user_orders,
    transition_order,
)
from services.wallets import (
    create_deposit_order,
    ensure_user_wallet,
    list_user_deposits,
)
from worker.tasks import fulfill_order

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/users/telegram", response_model=UserOut)
async def upsert_telegram_user(
    payload: TelegramUserUpsert,
    session: DbSession,
    _: InternalAuth,
) -> User:
    user = await session.scalar(
        select(User).where(User.telegram_id == payload.telegram_id)
    )

    if user is None:
        user = User(
            telegram_id=payload.telegram_id,
            telegram_username=payload.telegram_username,
        )
        session.add(user)
    else:
        user.telegram_username = payload.telegram_username

    await session.flush()
    await ensure_user_wallet(session, user.id)
    await session.commit()
    await session.refresh(user)
    return user


@router.get("/plans", response_model=list[PlanOut])
async def plans(
    session: DbSession,
    _: InternalAuth,
) -> list[Plan]:
    return list(
        (
            await session.scalars(
                select(Plan)
                .where(Plan.is_active.is_(True))
                .order_by(Plan.sort_order, Plan.months)
            )
        ).all()
    )


@router.get("/networks", response_model=list[NetworkOut])
async def networks(
    session: DbSession,
    _: InternalAuth,
) -> list[NetworkOut]:
    labels = {
        "TRC20": "USDT (TRC20)",
        "BEP20": "USDT (BEP20)",
        "ERC20": "USDT (ERC20)",
    }

    configured = set(
        (
            await session.scalars(
                select(Wallet.network)
                .where(Wallet.is_enabled.is_(True))
                .distinct()
            )
        ).all()
    )

    return [
        NetworkOut(code=code, label=labels[code])
        for code in settings.enabled_network_list
        if code in configured
    ]


@router.post("/orders", response_model=OrderOut)
async def create_internal_order(
    payload: OrderCreateInternal,
    session: DbSession,
    _: InternalAuth,
) -> Order:
    user = await session.scalar(
        select(User).where(User.telegram_id == payload.telegram_id)
    )

    if user is None:
        user = User(telegram_id=payload.telegram_id)
        session.add(user)
        await session.flush()

    order = await create_order(
        session,
        user=user,
        plan_id=payload.plan_id,
        target_username=payload.target_username,
        network=payload.network,
        payment_method=payload.payment_method,
        callback_url=str(payload.callback_url) if payload.callback_url else None,
    )

    await session.commit()

    created = await get_order_by_no(
        session,
        order.order_no,
    )

    if created.status == OrderStatus.PAID.value:
        try:
            fulfill_order.delay(created.id)
        except Exception as exc:
            await fail_and_refund_order(
                session,
                created,
                reason="Could not enqueue Premium fulfillment",
                actor_type="API",
            )
            await session.commit()
            raise ConflictError(
                "订单暂时无法进入处理队列，钱包余额已退回"
            ) from exc

    return created


# 必须放在 /orders/{order_no} 前面
@router.get("/orders", response_model=list[OrderOut])
async def list_internal_orders(
    telegram_id: int,
    session: DbSession,
    _: InternalAuth,
    limit: int = Query(10, ge=1, le=50),
) -> list[Order]:
    user = await session.scalar(
        select(User).where(User.telegram_id == telegram_id)
    )

    if user is None:
        return []

    return await list_user_orders(
        session,
        user_id=user.id,
        limit=limit,
    )


@router.get("/orders/{order_no}", response_model=OrderOut)
async def query_internal_order(
    order_no: str,
    telegram_id: int,
    session: DbSession,
    _: InternalAuth,
) -> Order:
    user = await session.scalar(
        select(User).where(User.telegram_id == telegram_id)
    )

    if user is None:
        raise NotFoundError("订单不存在")

    return await get_order_by_no(
        session,
        order_no,
        user_id=user.id,
    )


@router.get("/wallet", response_model=UserWalletOut)
async def wallet_summary(
    telegram_id: int,
    session: DbSession,
    _: InternalAuth,
) -> UserWallet:
    user = await session.scalar(
        select(User).where(User.telegram_id == telegram_id)
    )

    if user is None:
        raise NotFoundError("用户不存在")

    user_wallet = await ensure_user_wallet(
        session,
        user.id,
    )

    await session.commit()
    return user_wallet


@router.get(
    "/wallet/ledger",
    response_model=list[WalletLedgerEntryOut],
)
async def wallet_ledger(
    telegram_id: int,
    session: DbSession,
    _: InternalAuth,
    limit: int = Query(10, ge=1, le=50),
) -> list[WalletLedgerEntry]:
    user = await session.scalar(
        select(User).where(User.telegram_id == telegram_id)
    )

    if user is None:
        raise NotFoundError("用户不存在")

    user_wallet = await ensure_user_wallet(
        session,
        user.id,
    )

    await session.commit()

    return list(
        (
            await session.scalars(
                select(WalletLedgerEntry)
                .where(
                    WalletLedgerEntry.wallet_id == user_wallet.id
                )
                .order_by(
                    WalletLedgerEntry.created_at.desc()
                )
                .limit(limit)
            )
        ).all()
    )


@router.post(
    "/wallet/deposits",
    response_model=DepositOrderOut,
)
async def create_wallet_deposit(
    payload: DepositCreateInternal,
    session: DbSession,
    _: InternalAuth,
) -> DepositOrder:
    user = await session.scalar(
        select(User).where(
            User.telegram_id == payload.telegram_id
        )
    )

    if user is None:
        raise NotFoundError("用户不存在")

    deposit = await create_deposit_order(
        session,
        user=user,
        requested_amount=payload.amount,
        network=payload.network,
    )

    await session.commit()
    return deposit


# 必须放在 /wallet/deposits/{deposit_no} 前面
@router.get(
    "/wallet/deposits",
    response_model=list[DepositOrderOut],
)
async def list_wallet_deposits(
    telegram_id: int,
    session: DbSession,
    _: InternalAuth,
    limit: int = Query(10, ge=1, le=50),
) -> list[DepositOrder]:
    user = await session.scalar(
        select(User).where(User.telegram_id == telegram_id)
    )

    if user is None:
        return []

    return await list_user_deposits(
        session,
        user_id=user.id,
        limit=limit,
    )


@router.get(
    "/wallet/deposits/{deposit_no}",
    response_model=DepositOrderOut,
)
async def get_wallet_deposit(
    deposit_no: str,
    telegram_id: int,
    session: DbSession,
    _: InternalAuth,
) -> DepositOrder:
    deposit = await session.scalar(
        select(DepositOrder)
        .join(
            User,
            User.id == DepositOrder.user_id,
        )
        .where(
            DepositOrder.deposit_no == deposit_no,
            User.telegram_id == telegram_id,
        )
    )

    if deposit is None:
        raise NotFoundError("充值单不存在")

    return deposit

@router.post("/fragment/capture", response_model=FragmentCaptureOut)
async def capture_fragment_transaction(
    payload: FragmentCaptureIn,
    session: DbSession,
    _: InternalAuth,
) -> FragmentCaptureOut:
    """Accept a plaintext TON Connect request from the trusted browser worker.

    The endpoint is internal-token protected. It performs risk validation,
    wallet reservation and signer-boundary invocation. Mock signer mode never
    broadcasts funds.
    """
    order = await session.scalar(
        select(Order).where(Order.id == payload.order_id).with_for_update()
    )
    if order is None:
        raise NotFoundError("订单不存在")
    if order.status not in {OrderStatus.PAID.value, OrderStatus.PROCESSING.value}:
        raise ConflictError(f"订单状态不允许发货：{order.status}")
    if order.status == OrderStatus.PAID.value:
        await transition_order(
            session,
            order,
            OrderStatus.PROCESSING,
            reason="Fragment TON payment captured",
            actor_type="FRAGMENT_BROWSER",
        )

    captured = FragmentPaymentRequest.from_tonconnect(payload.request, expected_amount_nano=payload.expected_amount_nano)
    result = await prepare_fragment_payment(
        session,
        order_id=order.id,
        captured=captured,
    )
    await session.commit()
    return FragmentCaptureOut(
        transaction_id=result.transaction_id,
        wallet_code=result.wallet_code,
        status=result.status,
        external_message_hash=result.external_message_hash,
        broadcasted=result.broadcasted,
        signer_mode=result.signer_mode,
    )
