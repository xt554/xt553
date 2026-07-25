
from __future__ import annotations

import httpx

from core.config import settings


class RunnerApiClient:
    def __init__(self) -> None:
        self.base_url = settings.telegram_api_base_url.rstrip("/") + "/runner/fragment"
        self.client = httpx.AsyncClient(
            timeout=30,
            headers={"X-Fragment-Runner-Token": settings.fragment_runner_token},
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        return await self.client.request(method, self.base_url + path, **kwargs)

    async def status(self, payload: dict) -> dict:
        response = await self.request("POST", "/status", json=payload)
        response.raise_for_status()
        return response.json()
