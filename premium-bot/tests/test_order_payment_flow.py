from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from database.base import Base
from database.enums import OrderStatus, PaymentStatus
from database.models import Plan, User, Wallet
from services.orders import create_order
from services.payments import ChainTransfer, ingest_transfer


@pytest.mark.asyncio
async def test_create_order_and_confirm_payment() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        user = User(telegram_id=123456, telegram_username="buyer")
        plan = Plan(
            code="TEST_3M",
            name="Premium 3 months",
            months=3,
            price=Decimal("29"),
            sort_order=1,
        )
        wallet = Wallet(
            name="Test TRC20",
            network="TRC20",
            address="TTestPaymentAddress123456789012345",
            token_contract="TXLAQ63Xg1NAzckPwKHvzw7CSEmLMEqcdj",
            token_decimals=6,
            min_confirmations=20,
        )
        session.add_all([user, plan, wallet])
        await session.commit()

        order = await create_order(
            session,
            user=user,
            plan_id=plan.id,
            target_username="@target_user",
            network="TRC20",
        )
        await session.commit()
        assert order.order_no.startswith("NO")
        assert order.status == OrderStatus.WAIT_PAY.value
        assert order.payment_amount >= Decimal("29")

        first_seen = await ingest_transfer(
            session,
            ChainTransfer(
                network="TRC20",
                tx_hash="test-transaction",
                to_address=wallet.address,
                amount=order.payment_amount,
                confirmations=5,
            ),
        )
        await session.commit()
        assert first_seen.matched_order_id is None
        assert first_seen.transaction.status == PaymentStatus.DETECTED.value
        assert order.status == OrderStatus.WAIT_PAY.value

        confirmed = await ingest_transfer(
            session,
            ChainTransfer(
                network="TRC20",
                tx_hash="test-transaction",
                to_address=wallet.address,
                amount=order.payment_amount,
                confirmations=20,
            ),
        )
        await session.commit()
        assert confirmed.newly_paid
        assert confirmed.matched_order_id == order.id
        assert confirmed.transaction.status == PaymentStatus.MATCHED.value
        assert order.status == OrderStatus.PAID.value

    await engine.dispose()
