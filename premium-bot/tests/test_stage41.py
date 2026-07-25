import pytest

from database.enums import OrderStatus, can_transition
from services.premium import MockPremiumService


@pytest.mark.asyncio
async def test_mock_provider_never_reports_delivery_success() -> None:
    provider = MockPremiumService()
    created = await provider.create_order("@valid_user", 3)
    result = await provider.purchase(created.reference)
    assert result.status == "PROCESSING"


def test_stage41_completion_requires_confirmation_path() -> None:
    assert not can_transition(OrderStatus.PAID, OrderStatus.COMPLETED)
    assert can_transition(OrderStatus.CONFIRMING, OrderStatus.COMPLETED)
