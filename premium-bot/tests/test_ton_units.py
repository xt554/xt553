from decimal import Decimal

import pytest

from services.ton_units import nano_to_ton, ton_to_nano


def test_ton_conversion() -> None:
    assert ton_to_nano("50") == 50_000_000_000
    assert nano_to_ton(16_500_000_000) == Decimal("16.5")


def test_negative_ton_rejected() -> None:
    with pytest.raises(ValueError):
        ton_to_nano("-1")
