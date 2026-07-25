from __future__ import annotations

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from database.models import HotWallet


async def sync_hot_wallets(session: AsyncSession) -> int:
    wallets = list((await session.scalars(select(HotWallet).where(HotWallet.status != "DISABLED"))).all())
    headers = {"X-API-Key": settings.toncenter_api_key} if settings.toncenter_api_key else {}
    changed = 0
    async with httpx.AsyncClient(timeout=15) as client:
        for wallet in wallets:
            try:
                response = await client.get(
                    f"{settings.toncenter_v2_url.rstrip('/')}/getWalletInformation",
                    params={"address": wallet.address}, headers=headers,
                )
                response.raise_for_status(); data = response.json()
            except httpx.HTTPError:
                continue
            if not data.get("ok"):
                continue
            result = data.get("result") or {}
            balance = int(result.get("balance") or 0)
            seqno = int(result.get("seqno") or 0)
            if wallet.balance_nano != balance or wallet.last_seqno != seqno:
                wallet.balance_nano = balance
                wallet.last_seqno = seqno
                changed += 1
    return changed
