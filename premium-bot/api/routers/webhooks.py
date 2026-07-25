from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select

from api.deps import DbSession
from api.schemas import MessageResponse, PaymentWebhook, PremiumWebhook
from core.config import settings
from core.signatures import verify_signature
from database.enums import OrderStatus
from database.models import Order
from services.orders import fail_and_refund_order, transition_order
from services.payments import ChainTransfer, ingest_transfer
from worker.tasks import deliver_callback, fulfill_order

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def _signed_body(request: Request, signature: str | None, secret: str) -> bytes:
    body = await request.body()
    if not signature or not verify_signature(body, signature, secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid webhook signature")
    return body


@router.post("/payments", response_model=MessageResponse)
async def payment_webhook(
    request: Request,
    session: DbSession,
    x_payment_signature: str | None = Header(default=None),
) -> MessageResponse:
    body = await _signed_body(request, x_payment_signature, settings.payment_webhook_secret)
    try:
        payload = PaymentWebhook.model_validate_json(body)
    except PydanticValidationError as exc:
        raise HTTPException(422, detail=exc.errors()) from exc
    result = await ingest_transfer(
        session,
        ChainTransfer(
            network=payload.network,
            tx_hash=payload.tx_hash,
            to_address=payload.to_address,
            amount=payload.amount,
            confirmations=payload.confirmations,
            log_index=payload.log_index,
            block_number=payload.block_number,
            block_time=payload.block_time,
            from_address=payload.from_address,
            token_contract=payload.token_contract,
            raw_data=payload.raw_data,
        ),
    )
    await session.commit()
    if result.newly_paid and result.matched_order_id:
        fulfill_order.delay(result.matched_order_id)
        deliver_callback.delay(result.matched_order_id)
    return MessageResponse(
        message=(
            "matched"
            if result.matched_order_id or result.matched_deposit_id
            else result.transaction.status.lower()
        )
    )


@router.post("/premium", response_model=MessageResponse)
async def premium_webhook(
    request: Request,
    session: DbSession,
    x_premium_signature: str | None = Header(default=None),
) -> MessageResponse:
    body = await _signed_body(
        request,
        x_premium_signature,
        settings.premium_provider_token or settings.order_callback_secret,
    )
    payload = PremiumWebhook.model_validate_json(body)
    order = await session.scalar(
        select(Order).where(Order.premium_reference == payload.reference).with_for_update()
    )
    if order is None:
        raise HTTPException(404, "Unknown premium reference")
    normalized = payload.status.upper()
    active = {
        OrderStatus.PROCESSING.value,
        OrderStatus.WAIT_FRAGMENT.value,
        OrderStatus.WAIT_SIGN.value,
        OrderStatus.BROADCASTED.value,
        OrderStatus.CONFIRMING.value,
        OrderStatus.MANUAL_REVIEW.value,
    }
    if normalized in {"SUCCESS", "COMPLETED"} and order.status in active:
        await transition_order(
            session, order, OrderStatus.COMPLETED, reason=payload.message, actor_type="PROVIDER"
        )
    elif normalized in {"FAILED", "CANCELLED"} and order.status in active:
        await fail_and_refund_order(
            session, order, reason=payload.message or "Provider reported failure", actor_type="PROVIDER"
        )
    await session.commit()
    deliver_callback.delay(order.id)
    return MessageResponse(message="accepted")
