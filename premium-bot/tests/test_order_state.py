import pytest

from database.enums import OrderStatus, can_transition
from services.errors import ValidationError
from services.orders import normalize_telegram_username


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (OrderStatus.WAIT_PAY, OrderStatus.PAID),
        (OrderStatus.WAIT_PAY, OrderStatus.TIMEOUT),
        (OrderStatus.PAID, OrderStatus.PROCESSING),
        (OrderStatus.PROCESSING, OrderStatus.WAIT_FRAGMENT),
        (OrderStatus.WAIT_FRAGMENT, OrderStatus.WAIT_SIGN),
        (OrderStatus.WAIT_SIGN, OrderStatus.BROADCASTED),
        (OrderStatus.BROADCASTED, OrderStatus.CONFIRMING),
        (OrderStatus.CONFIRMING, OrderStatus.COMPLETED),
        (OrderStatus.PROCESSING, OrderStatus.FAILED),
        (OrderStatus.FAILED, OrderStatus.PROCESSING),
        (OrderStatus.FAILED, OrderStatus.REFUNDED),
        (OrderStatus.MANUAL_REVIEW, OrderStatus.PROCESSING),
        (OrderStatus.TIMEOUT, OrderStatus.PAID),
    ],
)
def test_allowed_transitions(source: OrderStatus, target: OrderStatus) -> None:
    assert can_transition(source, target)


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (OrderStatus.WAIT_PAY, OrderStatus.COMPLETED),
        (OrderStatus.PAID, OrderStatus.COMPLETED),
        (OrderStatus.COMPLETED, OrderStatus.PROCESSING),
        (OrderStatus.TIMEOUT, OrderStatus.PROCESSING),
    ],
)
def test_forbidden_transitions(source: OrderStatus, target: OrderStatus) -> None:
    assert not can_transition(source, target)


def test_username_normalization() -> None:
    assert normalize_telegram_username("valid_user") == "@valid_user"
    assert normalize_telegram_username(" @ValidUser ") == "@ValidUser"


@pytest.mark.parametrize("value", ["abc", "@bad-name", "@a", "@white space"])
def test_invalid_username(value: str) -> None:
    with pytest.raises(ValidationError):
        normalize_telegram_username(value)
