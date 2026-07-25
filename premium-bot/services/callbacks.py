from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy import select

from core.config import settings
from core.signatures import sign_payload
from database.models import Order, WebhookDelivery
from database.session import session_scope


async def deliver_order_callback(order_id: str, attempt: int = 1) -> bool:
    async with session_scope() as session:
        order = await session.scalar(select(Order).where(Order.id == order_id))
        if order is None or not order.callback_url:
            return True
        payload = {
            "event": "order.updated",
            "order_no": order.order_no,
            "status": order.status,
            "payment_method": order.payment_method,
            "network": order.network,
            "amount": str(order.payment_amount),
            "tx_hash": order.tx_hash,
            "premium_reference": order.premium_reference,
            "updated_at": order.updated_at.isoformat(),
        }
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        delivery = WebhookDelivery(
            order_id=order.id,
            event="order.updated",
            target_url=order.callback_url,
            attempt=attempt,
        )
        session.add(delivery)
        try:
            async with httpx.AsyncClient(timeout=settings.order_callback_timeout_seconds) as client:
                response = await client.post(
                    order.callback_url,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Premium-Signature": sign_payload(body, settings.order_callback_secret),
                    },
                )
            delivery.http_status = response.status_code
            delivery.response_body = response.text[:2000]
            if 200 <= response.status_code < 300:
                delivery.delivered_at = datetime.now(UTC)
                return True
        except httpx.HTTPError as exc:
            delivery.response_body = str(exc)[:2000]
        delivery.next_retry_at = datetime.now(UTC) + timedelta(minutes=min(2**attempt, 60))
        return False
