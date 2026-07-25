from __future__ import annotations

from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from database.enums import TonTransactionStatus
from database.models import TonTransaction


async def reconcile_ton_transactions(session: AsyncSession, *, limit: int = 100) -> int:
    rows = list((await session.scalars(
        select(TonTransaction).where(
            TonTransaction.status == TonTransactionStatus.BROADCASTED.value,
            TonTransaction.external_message_hash.is_not(None),
        ).order_by(TonTransaction.broadcast_at.asc()).limit(limit).with_for_update(skip_locked=True)
    )).all())
    if not rows:
        return 0
    headers = {"X-API-Key": settings.toncenter_api_key} if settings.toncenter_api_key else {}
    confirmed = 0
    async with httpx.AsyncClient(timeout=15) as client:
        for tx in rows:
            try:
                response = await client.get(
                    f"{settings.toncenter_v3_url.rstrip('/')}/messages",
                    params={"msg_hash": tx.external_message_hash, "limit": 1}, headers=headers,
                )
                response.raise_for_status(); data = response.json()
            except httpx.HTTPError as exc:
                tx.last_error = f"TON reconciliation failed: {exc}"[:500]
                continue
            if isinstance(data, list):
                messages = data
            else:
                messages = data.get("messages") or data.get("result") or []
            if not messages:
                continue
            message = messages[0] if isinstance(messages, list) else messages
            tx.status = TonTransactionStatus.CONFIRMED.value
            tx.confirmed_at = datetime.now(UTC)
            tx.tx_hash = str(message.get("tx_hash") or message.get("transaction_hash") or "") or None
            tx.tx_lt = str(message.get("created_lt") or message.get("lt") or "") or None
            tx.raw_chain_result = {**(tx.raw_chain_result or {}), "confirmation": message}
            confirmed += 1
    return confirmed
