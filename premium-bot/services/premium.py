from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

import httpx

from core.config import settings


@dataclass(slots=True)
class PremiumResult:
    status: str
    reference: str
    message: str = ""
    raw: dict[str, Any] | None = None


class PremiumService(ABC):
    """Stable integration boundary for a Telegram Premium fulfillment channel."""

    @abstractmethod
    async def create_order(self, username: str, months: int) -> PremiumResult:
        raise NotImplementedError

    @abstractmethod
    async def purchase(self, order_id: str) -> PremiumResult:
        raise NotImplementedError

    @abstractmethod
    async def query(self, order_id: str) -> PremiumResult:
        raise NotImplementedError


class MockPremiumService(PremiumService):
    async def create_order(self, username: str, months: int) -> PremiumResult:
        reference = f"mock_{uuid4().hex}"
        return PremiumResult("CREATED", reference, f"{username}: {months} months")

    async def purchase(self, order_id: str) -> PremiumResult:
        return PremiumResult("PROCESSING", order_id, "Mock mode: waiting for Fragment runner")

    async def query(self, order_id: str) -> PremiumResult:
        return PremiumResult("PROCESSING", order_id, "Mock mode: waiting for Fragment runner")


class WebhookPremiumService(PremiumService):
    def __init__(self) -> None:
        if not settings.premium_provider_url:
            raise RuntimeError("PREMIUM_PROVIDER_URL is required for webhook provider")
        self.base_url = settings.premium_provider_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {settings.premium_provider_token}",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> PremiumResult:
        async with httpx.AsyncClient(timeout=settings.premium_provider_timeout_seconds) as client:
            response = await client.request(
                method, f"{self.base_url}{path}", headers=self.headers, **kwargs
            )
            response.raise_for_status()
            data = response.json()
        return PremiumResult(
            status=str(data.get("status", "PROCESSING")).upper(),
            reference=str(data.get("order_id") or data.get("reference")),
            message=str(data.get("message", "")),
            raw=data,
        )

    async def create_order(self, username: str, months: int) -> PremiumResult:
        return await self._request("POST", "/orders", json={"username": username, "months": months})

    async def purchase(self, order_id: str) -> PremiumResult:
        return await self._request("POST", f"/orders/{order_id}/purchase")

    async def query(self, order_id: str) -> PremiumResult:
        return await self._request("GET", f"/orders/{order_id}")


def get_premium_service() -> PremiumService:
    if settings.premium_provider.lower() == "mock":
        return MockPremiumService()
    if settings.premium_provider.lower() == "webhook":
        return WebhookPremiumService()
    raise RuntimeError(f"Unknown PREMIUM_PROVIDER: {settings.premium_provider}")
