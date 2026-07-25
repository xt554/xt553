"""Create/update exactly three TON hot-wallet metadata records.

Usage:
  TON_WALLET_1_ADDRESS=... TON_WALLET_2_ADDRESS=... TON_WALLET_3_ADDRESS=... \
  python scripts/seed_ton_wallets.py

This script stores public addresses only. Never pass seed phrases or private keys.
"""
from __future__ import annotations

import asyncio
import os
from datetime import date

from sqlalchemy import select

from database.models import CircuitBreaker, HotWallet, PaymentWhitelist
from database.session import session_scope
from services.ton_units import ton_to_nano


async def main() -> None:
    addresses = [os.getenv(f"TON_WALLET_{i}_ADDRESS", "").strip() for i in range(1, 4)]
    if any(not address for address in addresses):
        raise SystemExit("Set TON_WALLET_1_ADDRESS, TON_WALLET_2_ADDRESS, TON_WALLET_3_ADDRESS")
    async with session_scope() as session:
        for index, address in enumerate(addresses, 1):
            code = f"ton-hot-{index}"
            wallet = await session.scalar(select(HotWallet).where(HotWallet.wallet_code == code))
            if wallet is None:
                wallet = HotWallet(
                    wallet_code=code,
                    address=address,
                    single_limit_nano=ton_to_nano("50"),
                    daily_limit_nano=ton_to_nano("100"),
                    minimum_balance_nano=ton_to_nano("1"),
                    target_balance_nano=ton_to_nano("50"),
                    maximum_balance_nano=ton_to_nano("100"),
                    spent_date=date.today(),
                )
                session.add(wallet)
            else:
                wallet.address = address
                wallet.single_limit_nano = ton_to_nano("50")
                wallet.daily_limit_nano = ton_to_nano("100")
            breaker_key = f"WALLET:{code}"
            if await session.get(CircuitBreaker, breaker_key) is None:
                session.add(CircuitBreaker(breaker_key=breaker_key))
        for destination in filter(None, os.getenv("TON_KNOWN_DESTINATIONS", "").split(",")):
            destination = destination.strip()
            row = await session.scalar(
                select(PaymentWhitelist).where(PaymentWhitelist.destination == destination)
            )
            if row is None:
                session.add(PaymentWhitelist(destination=destination, label="Fragment verified"))


if __name__ == "__main__":
    asyncio.run(main())
