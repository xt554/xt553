from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from database.models import CircuitBreaker


class CircuitOpen(RuntimeError):
    pass


async def assert_closed(session: AsyncSession, breaker_key: str) -> None:
    breaker = await session.scalar(
        select(CircuitBreaker).where(CircuitBreaker.breaker_key == breaker_key).with_for_update()
    )
    if breaker is None or breaker.state == "CLOSED":
        return
    now = datetime.now(UTC)
    if breaker.state == "OPEN" and breaker.cooldown_until and breaker.cooldown_until <= now:
        breaker.state = "HALF_OPEN"
        return
    raise CircuitOpen(f"Circuit breaker {breaker_key} is {breaker.state}: {breaker.reason or ''}")


async def record_success(session: AsyncSession, breaker_key: str) -> None:
    breaker = await session.scalar(
        select(CircuitBreaker).where(CircuitBreaker.breaker_key == breaker_key).with_for_update()
    )
    if breaker:
        breaker.state = "CLOSED"
        breaker.failure_count = 0
        breaker.opened_at = None
        breaker.cooldown_until = None
        breaker.reason = None


async def record_failure(session: AsyncSession, breaker_key: str, reason: str) -> None:
    breaker = await session.scalar(
        select(CircuitBreaker).where(CircuitBreaker.breaker_key == breaker_key).with_for_update()
    )
    if breaker is None:
        breaker = CircuitBreaker(breaker_key=breaker_key)
        session.add(breaker)
    breaker.failure_count += 1
    breaker.reason = reason[:500]
    if breaker.failure_count >= settings.ton_circuit_failure_threshold:
        now = datetime.now(UTC)
        breaker.state = "OPEN"
        breaker.opened_at = now
        breaker.cooldown_until = now + timedelta(seconds=settings.ton_circuit_cooldown_seconds)
