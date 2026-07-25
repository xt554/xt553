from core.signatures import sign_payload, verify_signature


def test_webhook_signature() -> None:
    body = b'{"order":"NO1","status":"SUCCESS"}'
    signature = sign_payload(body, "secret")
    assert verify_signature(body, signature, "secret")
    assert not verify_signature(body + b" ", signature, "secret")
