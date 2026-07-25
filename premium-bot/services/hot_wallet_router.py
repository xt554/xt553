from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from database.enums import TonTransactionStatus, WalletReservationStatus
from database.models import HotWallet, TonTransaction, WalletReservation
from services.ton_units import ton_to_nano
from services.ton_address import normalize_ton_address


class NoHotWalletAvailable(RuntimeError):
    pass


_IN_FLIGHT_STATUSES = (
    TonTransactionStatus.SIGNING.value,
    TonTransactionStatus.BROADCASTED.value,
    TonTransactionStatus.MANUAL_REVIEW.value,
)


def _wallet_score(wallet: HotWallet, *, amount_nano: int, daily_spent: int) -> tuple[float, ...]:
    available = max(0, wallet.balance_nano - wallet.reserved_nano)
    daily_limit = max(1, wallet.daily_limit_nano)
    daily_ratio = daily_spent / daily_limit
    remaining_after = max(0, available - amount_nano)
    balance_ratio = remaining_after / max(1, wallet.target_balance_nano or wallet.maximum_balance_nano)
    last_used = wallet.last_used_at.timestamp() if wallet.last_used_at else 0.0
    return (
        float(wallet.priority),
        daily_ratio,
        float(wallet.consecutive_failure_count),
        -balance_ratio,
        last_used,
    )


async def reserve_hot_wallet(
    session: AsyncSession,
    *,
    order_id: str,
    amount_nano: int,
    source_address: str | None = None,
) -> WalletReservation:
    existing = await session.scalar(
        select(WalletReservation).where(WalletReservation.order_id == order_id).with_for_update()
    )
    if existing:
        return existing

    now = datetime.now(UTC)
    today = now.date()
    in_flight_wallet_ids = set(
        (
            await session.scalars(
                select(TonTransaction.wallet_id).where(
                    TonTransaction.status.in_(_IN_FLIGHT_STATUSES)
                )
            )
        ).all()
    )
    wallets = list(
        (
            await session.scalars(
                select(HotWallet)
                .where(HotWallet.status == "ACTIVE")
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    wallet_daily_cap = ton_to_nano(settings.ton_wallet_daily_limit)
    eligible: list[tuple[tuple[float, ...], HotWallet]] = []
    for wallet in wallets:
        if wallet.id in in_flight_wallet_ids:
            continue
        if source_address and settings.ton_require_source_match:
            if normalize_ton_address(wallet.address) != normalize_ton_address(source_address):
                continue
        daily_spent = wallet.daily_spent_nano if wallet.spent_date == today else 0
        available = wallet.balance_nano - wallet.reserved_nano
        if amount_nano > wallet.single_limit_nano:
            continue
        if daily_spent + amount_nano > min(wallet.daily_limit_nano, wallet_daily_cap):
            continue
        if available < amount_nano + wallet.minimum_balance_nano:
            continue
        eligible.append((_wallet_score(wallet, amount_nano=amount_nano, daily_spent=daily_spent), wallet))

    if not eligible:
        if source_address and settings.ton_require_source_match:
            raise NoHotWalletAvailable(
                "No eligible hot wallet matches the TON Connect source address"
            )
        raise NoHotWalletAvailable(
            "No eligible hot wallet; refill is manual and no wallet has capacity"
        )

    _, wallet = min(eligible, key=lambda item: item[0])
    reservation = WalletReservation(
        order_id=order_id,
        wallet_id=wallet.id,
        reserved_nano=amount_nano,
        status=WalletReservationStatus.RESERVED.value,
        expires_at=now + timedelta(minutes=settings.ton_reservation_minutes),
    )
    wallet.reserved_nano += amount_nano
    wallet.last_used_at = now
    session.add(reservation)
    await session.flush()
    return reservation


async def release_wallet_reservation(
    session: AsyncSession,
    reservation: WalletReservation,
    *,
    status: WalletReservationStatus = WalletReservationStatus.RELEASED,
) -> bool:
    if reservation.status != WalletReservationStatus.RESERVED.value:
        return False
    wallet = await session.scalar(
        select(HotWallet).where(HotWallet.id == reservation.wallet_id).with_for_update()
    )
    if wallet is not None:
        wallet.reserved_nano = max(0, wallet.reserved_nano - reservation.reserved_nano)
    reservation.status = status.value
    reservation.released_at = datetime.now(UTC)
    return True


async def expire_wallet_reservations(session: AsyncSession, *, limit: int = 200) -> int:
    now = datetime.now(UTC)
    reservations = list(
        (
            await session.scalars(
                select(WalletReservation)
                .where(
                    WalletReservation.status == WalletReservationStatus.RESERVED.value,
                    WalletReservation.expires_at <= now,
                )
                .order_by(WalletReservation.expires_at.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    released = 0
    for reservation in reservations:
        if await release_wallet_reservation(
            session,
            reservation,
            status=WalletReservationStatus.EXPIRED,
        ):
            released += 1
    return released
