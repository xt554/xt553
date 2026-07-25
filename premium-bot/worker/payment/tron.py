from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx

from core.config import settings
from database.models import Wallet
from services.payments import ChainTransfer
from worker.payment.base import PaymentAdapter


def ensure_utc(value: datetime | None) -> datetime | None:
    """将数据库返回的 naive datetime 统一视为 UTC。"""
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


class TronUsdtAdapter(PaymentAdapter):
    async def scan_wallet(self, wallet: Wallet) -> list[ChainTransfer]:
        headers: dict[str, str] = {}

        if settings.trongrid_api_key:
            headers["TRON-PRO-API-KEY"] = settings.trongrid_api_key

        last_scanned_at = ensure_utc(wallet.last_scanned_at)

        params: dict[str, str | int] = {
            "only_confirmed": "true",
            "limit": 200,
            "order_by": "block_timestamp,asc",
            "contract_address": (
                wallet.token_contract or settings.trc20_usdt_contract
            ),
        }

        if last_scanned_at is not None:
            overlap = last_scanned_at - timedelta(minutes=5)
            params["min_timestamp"] = int(overlap.timestamp() * 1000)

        async with httpx.AsyncClient(
            timeout=30,
            headers=headers,
        ) as client:
            response = await client.get(
                f"{settings.trongrid_api_url.rstrip('/')}/v1/accounts/"
                f"{wallet.address}/transactions/trc20",
                params=params,
            )
            response.raise_for_status()
            payload = response.json()

        transfers: list[ChainTransfer] = []
        max_timestamp = last_scanned_at

        for item in payload.get("data", []):
            timestamp_ms = int(item.get("block_timestamp", 0))

            if timestamp_ms <= 0:
                continue

            block_time = datetime.fromtimestamp(
                timestamp_ms / 1000,
                tz=UTC,
            )

            if max_timestamp is None or block_time > max_timestamp:
                max_timestamp = block_time

            token_info = item.get("token_info") or {}
            decimals = int(
                token_info.get("decimals", wallet.token_decimals)
            )

            amount = (
                Decimal(str(item["value"]))
                / (Decimal(10) ** decimals)
            )

            transfers.append(
                ChainTransfer(
                    network="TRC20",
                    tx_hash=item["transaction_id"],
                    log_index=0,
                    block_number=None,
                    block_time=block_time,
                    from_address=item.get("from"),
                    to_address=item.get("to", wallet.address),
                    token_contract=token_info.get("address"),
                    amount=amount,
                    confirmations=wallet.min_confirmations,
                    raw_data=item,
                )
            )

        # MySQL DATETIME 通常不保存时区。
        # 写回 naive UTC，下一次读取时再通过 ensure_utc 恢复。
        final_timestamp = max_timestamp or datetime.now(UTC)
        wallet.last_scanned_at = final_timestamp.replace(tzinfo=None)

        return transfers