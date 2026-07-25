from decimal import Decimal

from services.payments import ChainTransfer


def test_chain_transfer_preserves_decimal_amount() -> None:
    transfer = ChainTransfer(
        network="TRC20",
        tx_hash="tx",
        to_address="TAddress",
        amount=Decimal("29.0371"),
        confirmations=20,
    )
    assert transfer.amount == Decimal("29.0371")
    assert transfer.network == "TRC20"
