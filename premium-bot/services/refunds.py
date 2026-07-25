from __future__ import annotations

import httpx
from sqlalchemy import select

from core.config import settings
from database.enums import RefundStatus
from database.models import Refund
from database.session import session_scope


async def execute_refund(refund_id: str) -> None:
    if not settings.refund_provider_url:
        raise RuntimeError("REFUND_PROVIDER_URL is not configured")
    async with session_scope() as session:
        refund = await session.scalar(
            select(Refund).where(Refund.id == refund_id).with_for_update()
        )
        if refund is None or refund.status != RefundStatus.REQUESTED.value:
            return
        refund.status = RefundStatus.PROCESSING.value
        await session.flush()
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    settings.refund_provider_url,
                    headers={"Authorization": f"Bearer {settings.refund_provider_token}"},
                    json={
                        "reference": refund.id,
                        "network": refund.network,
                        "address": refund.destination_address,
                        "amount": str(refund.amount),
                        "currency": "USDT",
                    },
                )
                response.raise_for_status()
                data = response.json()
            refund.status = RefundStatus.SUCCESS.value
            refund.provider_reference = str(data.get("reference", ""))
            refund.tx_hash = str(data.get("tx_hash", ""))
        except Exception as exc:
            refund.status = RefundStatus.FAILED.value
            refund.failure_reason = str(exc)[:1000]
            raise
