from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from database.base import Base
from database.enums import (
    DepositStatus,
    OrderStatus,
    PaymentMethod,
    WalletEntryType,
)
from database.models import Plan, User, UserWallet, Wallet, WalletLedgerEntry
from services.orders import create_order, transition_order
from services.payments import ChainTransfer, ingest_transfer
from services.wallets import create_deposit_order, ensure_user_wallet


@pytest.mark.asyncio
async def test_deposit_balance_payment_and_automatic_refund() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        user = User(telegram_id=998877, telegram_username="wallet_buyer")
        plan = Plan(
            code="WALLET_3M",
            name="Premium 3 months",
            months=3,
            price=Decimal("29"),
            sort_order=1,
        )
        receive_wallet = Wallet(
            name="Wallet deposits",
            network="TRC20",
            address="TWalletDepositAddress123456789012345",
            token_contract="TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj",
            token_decimals=6,
            min_confirmations=20,
        )
        session.add_all([user, plan, receive_wallet])
        await session.commit()

        user_wallet = await ensure_user_wallet(session, user.id)
        deposit = await create_deposit_order(
            session,
            user=user,
            requested_amount=Decimal("50"),
            network="TRC20",
        )
        await session.commit()
        assert deposit.status == DepositStatus.WAIT_PAY.value
        assert deposit.payment_amount >= Decimal("50")

        credited = await ingest_transfer(
            session,
            ChainTransfer(
                network="TRC20",
                tx_hash="wallet-deposit-transaction",
                to_address=receive_wallet.address,
                amount=deposit.payment_amount,
                confirmations=20,
            ),
        )
        await session.commit()
        await session.refresh(user_wallet)
        assert credited.newly_credited
        assert credited.matched_deposit_id == deposit.id
        assert deposit.status == DepositStatus.CONFIRMED.value
        assert user_wallet.available_balance == deposit.payment_amount

        duplicate = await ingest_transfer(
            session,
            ChainTransfer(
                network="TRC20",
                tx_hash="wallet-deposit-transaction",
                to_address=receive_wallet.address,
                amount=deposit.payment_amount,
                confirmations=25,
            ),
        )
        await session.commit()
        await session.refresh(user_wallet)
        assert not duplicate.newly_credited
        assert user_wallet.available_balance == deposit.payment_amount

        order = await create_order(
            session,
            user=user,
            plan_id=plan.id,
            target_username="@target_user",
            network=None,
            payment_method=PaymentMethod.WALLET_BALANCE.value,
        )
        await session.commit()
        await session.refresh(user_wallet)
        assert order.status == OrderStatus.PAID.value
        assert order.payment_method == PaymentMethod.WALLET_BALANCE.value
        assert user_wallet.available_balance == deposit.payment_amount - plan.price

        await transition_order(session, order, OrderStatus.PROCESSING)
        await transition_order(
            session,
            order,
            OrderStatus.FAILED,
            reason="Provider rejected test order",
        )
        await session.commit()
        await session.refresh(user_wallet)
        assert order.balance_refunded_at is not None
        assert user_wallet.available_balance == deposit.payment_amount

        entries = list(
            (
                await session.scalars(
                    select(WalletLedgerEntry)
                    .where(WalletLedgerEntry.wallet_id == user_wallet.id)
                    .order_by(WalletLedgerEntry.created_at)
                )
            ).all()
        )
        assert [entry.entry_type for entry in entries] == [
            WalletEntryType.DEPOSIT.value,
            WalletEntryType.ORDER_PAYMENT.value,
            WalletEntryType.ORDER_REFUND.value,
        ]
        assert len((await session.scalars(select(UserWallet))).all()) == 1

    await engine.dispose()
