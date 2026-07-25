from core.signer_auth import signer_signature, verify_signer_signature


def test_signer_hmac_roundtrip() -> None:
    body = b'{"hello":"world"}'
    signature = signer_signature("secret", "123", "nonce", body)
    assert verify_signer_signature("secret", "123", "nonce", body, signature)
    assert not verify_signer_signature("wrong", "123", "nonce", body, signature)
