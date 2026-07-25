from __future__ import annotations

import asyncio
import logging
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.security import hash_password
from database.enums import FragmentAccountStatus, PaymentNetwork, UserRole
from database.models import CircuitBreaker, FragmentAccount, Plan, SystemSetting, User, Wallet
from database.session import session_scope

logger = logging.getLogger(__name__)

DEFAULT_PLANS = (
    {"code": "PREMIUM_3M", "name": "Telegram Premium 3个月", "months": 3, "price": "29"},
    {"code": "PREMIUM_6M", "name": "Telegram Premium 6个月", "months": 6, "price": "55"},
    {"code": "PREMIUM_12M", "name": "Telegram Premium 12个月", "months": 12, "price": "99"},
)


async def seed_reference_data(session: AsyncSession) -> None:
    for index, item in enumerate(DEFAULT_PLANS, start=1):
        existing_plan = await session.scalar(select(Plan).where(Plan.code == item["code"]))
        if existing_plan is None:
            session.add(
                Plan(
                    code=item["code"],
                    name=item["name"],
                    months=item["months"],
                    price=Decimal(str(item["price"])),
                    sort_order=index,
                )
            )

    admin = await session.scalar(select(User).where(User.username == settings.admin_username))
    if admin is None:
        session.add(
            User(
                username=settings.admin_username,
                password_hash=hash_password(settings.admin_password),
                role=UserRole.ADMIN.value,
                is_active=True,
            )
        )

    wallet_settings = {
        PaymentNetwork.TRC20: (
            settings.trc20_receive_address,
            settings.trc20_usdt_contract,
            settings.trc20_confirmations,
            6,
        ),
        PaymentNetwork.BEP20: (
            settings.bep20_receive_address,
            settings.bep20_usdt_contract,
            settings.bep20_confirmations,
            18,
        ),
        PaymentNetwork.ERC20: (
            settings.erc20_receive_address,
            settings.erc20_usdt_contract,
            settings.erc20_confirmations,
            6,
        ),
    }
    for network, (address, contract, confirmations, decimals) in wallet_settings.items():
        if not address:
            continue
        existing_wallet = await session.scalar(
            select(Wallet).where(Wallet.network == network.value, Wallet.address == address)
        )
        if existing_wallet is None:
            session.add(
                Wallet(
                    name=f"Default {network.value} wallet",
                    network=network.value,
                    address=address,
                    token_contract=contract,
                    token_decimals=decimals,
                    min_confirmations=confirmations,
                )
            )

    for code, profile_name in settings.fragment_runner_account_list:
        account = await session.scalar(select(FragmentAccount).where(FragmentAccount.code == code))
        if account is None:
            session.add(
                FragmentAccount(
                    code=code,
                    display_name=code,
                    profile_name=profile_name,
                    status=FragmentAccountStatus.ACTIVE.value,
                    is_enabled=True,
                )
            )

    for breaker_key in ("GLOBAL", "FRAGMENT_PROVIDER"):
        if await session.get(CircuitBreaker, breaker_key) is None:
            session.add(CircuitBreaker(breaker_key=breaker_key))

    default_settings = {
        "order_expire_minutes": (
            settings.order_expire_minutes,
            "待支付订单有效分钟数（1-1440）",
        ),
        "maintenance_mode": (False, "维护模式开关"),
        "support_contact": ("", "客服联系方式"),
    }
    for key, (value, description) in default_settings.items():
        existing_setting = await session.get(SystemSetting, key)
        if existing_setting is None:
            session.add(
                SystemSetting(
                    key=key,
                    value=value,
                    description=description,
                    is_public=key in {"maintenance_mode", "support_contact"},
                )
            )


async def main() -> None:
    async with session_scope() as session:
        await seed_reference_data(session)
    logger.info("Reference data seeded")


if __name__ == "__main__":
    asyncio.run(main())
