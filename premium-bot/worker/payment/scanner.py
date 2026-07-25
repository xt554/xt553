from __future__ import annotations

import logging

from sqlalchemy import select

from database.models import Wallet
from database.session import session_scope
from services.payments import ingest_transfer
from worker.payment.evm import evm_adapter_for
from worker.payment.tron import TronUsdtAdapter

logger = logging.getLogger(__name__)


async def scan_all_wallets() -> list[str]:
    paid_order_ids: set[str] = set()
    async with session_scope() as session:
        wallets = (
            await session.scalars(
                select(Wallet)
                .where(Wallet.is_enabled.is_(True))
                .order_by(Wallet.network, Wallet.created_at)
            )
        ).all()
        for wallet in wallets:
            try:
                adapter = (
                    TronUsdtAdapter()
                    if wallet.network == "TRC20"
                    else evm_adapter_for(wallet.network)
                )
                transfers = await adapter.scan_wallet(wallet)
                for transfer in transfers:
                    result = await ingest_transfer(session, transfer)
                    if result.newly_paid and result.matched_order_id:
                        paid_order_ids.add(result.matched_order_id)
            except Exception:
                logger.exception(
                    "Payment scan failed",
                    extra={"network": wallet.network, "wallet_id": wallet.id},
                )
    return list(paid_order_ids)
