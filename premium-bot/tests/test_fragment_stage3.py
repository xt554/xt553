from time import time
import pytest
from services.fragment_capture import FragmentPaymentRequest, FragmentCaptureError
from services.ton_address import normalize_ton_address

def test_known_addresses_normalize():
    assert normalize_ton_address("UQDt7K7GNl48mpQtXKLzafD8Vv2gJtUPEvKDMp7Z0JkWtTWr").startswith("0:")

def test_capture_rejects_items():
    with pytest.raises(FragmentCaptureError):
        FragmentPaymentRequest.from_tonconnect({"validUntil": int(time())+60, "items": []})

def test_capture_records_state_and_extra():
    r=FragmentPaymentRequest.from_tonconnect({"validUntil": int(time())+60,"network":"-239",\
      "messages":[{"address":"UQDt7K7GNl48mpQtXKLzafD8Vv2gJtUPEvKDMp7Z0JkWtTWr","amount":"1","payload":"dA==","stateInit":"x","extraCurrency":{"1":"2"}}]}, expected_amount_nano=1)
    assert r.state_init == "x" and r.extra_currency == {"1":"2"}
