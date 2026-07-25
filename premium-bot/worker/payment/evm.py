from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx

from core.config import settings
from database.models import Wallet
from services.payments import ChainTransfer
from worker.payment.base import PaymentAdapter

TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


class EvmUsdtAdapter(PaymentAdapter):
    def __init__(self, network: str, rpc_url: str, default_contract: str) -> None:
        self.network = network
        self.rpc_url = rpc_url
        self.default_contract = default_contract
        self.request_id = 0

    async def _rpc(self, client: httpx.AsyncClient, method: str, params: list[Any]) -> Any:
        self.request_id += 1
        response = await client.post(
            self.rpc_url,
            json={
                "jsonrpc": "2.0",
                "id": self.request_id,
                "method": method,
                "params": params,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise RuntimeError(f"{self.network} RPC error: {payload['error']}")
        return payload["result"]

    async def scan_wallet(self, wallet: Wallet) -> list[ChainTransfer]:
        if not self.rpc_url:
            return []
        async with httpx.AsyncClient(timeout=30) as client:
            latest_hex = await self._rpc(client, "eth_blockNumber", [])
            latest = int(latest_hex, 16)
            if wallet.last_scanned_block is None:
                from_block = max(0, latest - 100)
            else:
                from_block = max(0, wallet.last_scanned_block - 20)
            to_block = min(
                latest,
                from_block + max(1, settings.payment_scan_block_chunk) - 1,
            )
            address_topic = "0x" + wallet.address.lower().removeprefix("0x").rjust(64, "0")
            logs = await self._rpc(
                client,
                "eth_getLogs",
                [
                    {
                        "fromBlock": hex(from_block),
                        "toBlock": hex(to_block),
                        "address": wallet.token_contract or self.default_contract,
                        "topics": [TRANSFER_TOPIC, None, address_topic],
                    }
                ],
            )
        wallet.last_scanned_block = to_block
        wallet.last_scanned_at = datetime.now(UTC)
        transfers: list[ChainTransfer] = []
        divisor = Decimal(10) ** wallet.token_decimals
        for item in logs:
            block_number = int(item["blockNumber"], 16)
            topics = item.get("topics", [])
            transfers.append(
                ChainTransfer(
                    network=self.network,
                    tx_hash=item["transactionHash"],
                    log_index=int(item["logIndex"], 16),
                    block_number=block_number,
                    block_time=None,
                    from_address=("0x" + topics[1][-40:] if len(topics) > 1 else None),
                    to_address="0x" + topics[2][-40:],
                    token_contract=item.get("address"),
                    amount=Decimal(int(item["data"], 16)) / divisor,
                    confirmations=max(0, latest - block_number + 1),
                    raw_data=item,
                )
            )
        return transfers


def evm_adapter_for(network: str) -> EvmUsdtAdapter:
    if network == "BEP20":
        return EvmUsdtAdapter(
            network,
            settings.bep20_rpc_url,
            settings.bep20_usdt_contract,
        )
    return EvmUsdtAdapter(
        network,
        settings.erc20_rpc_url,
        settings.erc20_usdt_contract,
    )
