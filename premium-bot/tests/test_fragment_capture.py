import pytest

from services.fragment_capture import FragmentCaptureError, FragmentPaymentRequest


def test_parse_tonconnect_request() -> None:
    request = FragmentPaymentRequest.from_tonconnect(
        {
            "valid_until": 2_000_000_000,
            "network": "-239",
            "messages": [
                {"address": "UQDt7K7GNl48mpQtXKLzafD8Vv2gJtUPEvKDMp7Z0JkWtTWr", "amount": "1000000000", "payload": "dGVzdA=="}
            ],
        }
    )
    assert request.destination == "UQDt7K7GNl48mpQtXKLzafD8Vv2gJtUPEvKDMp7Z0JkWtTWr"
    assert request.amount_nano == 1_000_000_000
    assert len(request.payload_hash) == 64


def test_reject_multiple_messages() -> None:
    with pytest.raises(FragmentCaptureError):
        FragmentPaymentRequest.from_tonconnect(
            {"valid_until": 1, "messages": [{"address": "a"}, {"address": "b"}]}
        )
