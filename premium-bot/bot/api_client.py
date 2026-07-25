from __future__ import annotations

from typing import Any, cast

import httpx

from core.config import settings


class BotAPIError(RuntimeError):
    pass


class PremiumAPIClient:
    def __init__(self) -> None:
        self.base_url = settings.telegram_api_base_url.rstrip("/")
        self.headers = {
            "X-Internal-Token": settings.internal_api_token,
        }

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        async with httpx.AsyncClient(
            timeout=15,
            headers=self.headers,
        ) as client:
            response = await client.request(
                method,
                f"{self.base_url}{path}",
                **kwargs,
            )

        if response.status_code >= 400:
            try:
                detail = response.json().get(
                    "detail",
                    "服务暂时不可用",
                )
            except ValueError:
                detail = "服务暂时不可用"

            raise BotAPIError(str(detail))

        return response.json()

    async def register_user(
        self,
        telegram_id: int,
        telegram_username: str | None,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self._request(
                "POST",
                "/internal/users/telegram",
                json={
                    "telegram_id": telegram_id,
                    "telegram_username": telegram_username,
                },
            ),
        )

    async def plans(self) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            await self._request(
                "GET",
                "/internal/plans",
            ),
        )

    async def networks(self) -> list[dict[str, str]]:
        return cast(
            list[dict[str, str]],
            await self._request(
                "GET",
                "/internal/networks",
            ),
        )

    async def create_order(
        self,
        *,
        telegram_id: int,
        plan_id: str,
        target_username: str,
        network: str | None,
        payment_method: str = "ONCHAIN",
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self._request(
                "POST",
                "/internal/orders",
                json={
                    "telegram_id": telegram_id,
                    "plan_id": plan_id,
                    "target_username": target_username,
                    "network": network,
                    "payment_method": payment_method,
                },
            ),
        )

    async def order(
        self,
        order_no: str,
        telegram_id: int,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self._request(
                "GET",
                f"/internal/orders/{order_no}",
                params={
                    "telegram_id": telegram_id,
                },
            ),
        )

    async def orders(
        self,
        telegram_id: int,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            await self._request(
                "GET",
                "/internal/orders",
                params={
                    "telegram_id": telegram_id,
                    "limit": limit,
                },
            ),
        )

    async def wallet(
        self,
        telegram_id: int,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self._request(
                "GET",
                "/internal/wallet",
                params={
                    "telegram_id": telegram_id,
                },
            ),
        )

    async def wallet_ledger(
        self,
        telegram_id: int,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            await self._request(
                "GET",
                "/internal/wallet/ledger",
                params={
                    "telegram_id": telegram_id,
                    "limit": limit,
                },
            ),
        )

    async def create_deposit(
        self,
        *,
        telegram_id: int,
        amount: str,
        network: str,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self._request(
                "POST",
                "/internal/wallet/deposits",
                json={
                    "telegram_id": telegram_id,
                    "amount": amount,
                    "network": network,
                },
            ),
        )

    async def deposits(
        self,
        telegram_id: int,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            await self._request(
                "GET",
                "/internal/wallet/deposits",
                params={
                    "telegram_id": telegram_id,
                    "limit": limit,
                },
            ),
        )

    async def deposit(
        self,
        deposit_no: str,
        telegram_id: int,
    ) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            await self._request(
                "GET",
                f"/internal/wallet/deposits/{deposit_no}",
                params={
                    "telegram_id": telegram_id,
                },
            ),
        )


api_client = PremiumAPIClient()