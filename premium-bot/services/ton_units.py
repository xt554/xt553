from decimal import Decimal, InvalidOperation, ROUND_DOWN

NANO_PER_TON = 1_000_000_000


def ton_to_nano(value: Decimal | str | int) -> int:
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Invalid TON amount") from exc
    if amount < 0:
        raise ValueError("TON amount cannot be negative")
    return int((amount * NANO_PER_TON).quantize(Decimal("1"), rounding=ROUND_DOWN))


def nano_to_ton(value: int) -> Decimal:
    return Decimal(value) / Decimal(NANO_PER_TON)
