from __future__ import annotations

import base64
import binascii


class TonAddressError(ValueError):
    pass


def _crc16_xmodem(data: bytes) -> int:
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def normalize_ton_address(value: str) -> str:
    """Return canonical raw ``workchain:hex`` form for raw or TEP-2 addresses."""
    value = value.strip()
    if ":" in value:
        wc_text, account = value.split(":", 1)
        try:
            wc = int(wc_text)
        except ValueError as exc:
            raise TonAddressError("Invalid raw TON workchain") from exc
        account = account.lower()
        if len(account) != 64:
            raise TonAddressError("Invalid raw TON account length")
        try:
            bytes.fromhex(account)
        except ValueError as exc:
            raise TonAddressError("Invalid raw TON account") from exc
        return f"{wc}:{account}"
    padded = value.replace("-", "+").replace("_", "/")
    padded += "=" * (-len(padded) % 4)
    try:
        decoded = base64.b64decode(padded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise TonAddressError("Invalid user-friendly TON address") from exc
    if len(decoded) != 36:
        raise TonAddressError("Invalid user-friendly TON address length")
    body, checksum = decoded[:34], decoded[34:]
    if _crc16_xmodem(body).to_bytes(2, "big") != checksum:
        raise TonAddressError("Invalid TON address checksum")
    wc = int.from_bytes(body[1:2], "big", signed=True)
    return f"{wc}:{body[2:34].hex()}"
