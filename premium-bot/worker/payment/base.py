from __future__ import annotations

from abc import ABC, abstractmethod

from database.models import Wallet
from services.payments import ChainTransfer


class PaymentAdapter(ABC):
    @abstractmethod
    async def scan_wallet(self, wallet: Wallet) -> list[ChainTransfer]:
        raise NotImplementedError
