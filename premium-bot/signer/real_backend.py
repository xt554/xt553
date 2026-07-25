from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import httpx

from core.config import settings
from signer.schemas import SignerRequest, SignerResponse


class RealSignerError(RuntimeError): pass

async def _wallet_seqno(address: str) -> int:
    headers = {"X-API-Key": settings.toncenter_api_key} if settings.toncenter_api_key else {}
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.get(f"{settings.toncenter_v2_url.rstrip('/')}/getWalletInformation",
                                    params={"address": address}, headers=headers)
        response.raise_for_status(); data = response.json()
    if not data.get("ok"):
        raise RealSignerError(f"TON Center wallet query failed: {data}")
    return int((data.get("result") or {}).get("seqno") or 0)

def _load_mnemonic(wallet_code: str) -> list[str]:
    path = Path(settings.ton_signer_key_dir) / f"{wallet_code}.mnemonic"
    if not path.is_file():
        raise RealSignerError(f"Missing signer secret file for {wallet_code}")
    words = path.read_text(encoding="utf-8").strip().split()
    if len(words) not in {12, 18, 24}:
        raise RealSignerError("Invalid mnemonic word count")
    return words

async def sign_and_broadcast_real(payload: SignerRequest) -> SignerResponse:
    try:
        from tonsdk.boc import Cell
        from tonsdk.contract.wallet import Wallets, WalletVersionEnum
        from tonsdk.utils import bytes_to_b64str
    except ImportError as exc:
        raise RealSignerError("tonsdk is not installed in signer image") from exc
    words = _load_mnemonic(payload.wallet_code)
    _, _, _, wallet = Wallets.from_mnemonics(words, WalletVersionEnum.v4r2, 0)
    expected = settings.ton_signer_wallet_address_map.get(payload.wallet_code)
    actual = wallet.address.to_string(True, True, False)
    if expected and actual != expected:
        # Friendly bounce flags may differ; API already checked canonical source.
        from services.ton_address import normalize_ton_address
        if normalize_ton_address(actual) != normalize_ton_address(expected):
            raise RealSignerError("Mnemonic does not match configured wallet address")
    seqno = await _wallet_seqno(actual)
    parsed = Cell.one_from_boc(base64.b64decode(payload.payload_boc))
    body = parsed[0] if isinstance(parsed, (list, tuple)) else parsed
    query = wallet.create_transfer_message(to_addr=payload.destination, amount=payload.amount_nano,
        seqno=seqno, payload=body, send_mode=settings.ton_signer_send_mode)
    boc = bytes_to_b64str(query["message"].to_boc(False))
    headers = {"X-API-Key": settings.toncenter_api_key} if settings.toncenter_api_key else {}
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(f"{settings.toncenter_v2_url.rstrip('/')}/sendBocReturnHash",
                                     json={"boc": boc}, headers=headers)
        response.raise_for_status(); data = response.json()
    if not data.get("ok"):
        raise RealSignerError(f"TON Center rejected BoC: {data}")
    result = data.get("result")
    if isinstance(result, str):
        message_hash = result
    elif isinstance(result, dict):
        message_hash = str(result.get("hash") or result.get("message_hash") or "")
    else:
        result = {}
        message_hash = ""
    if not message_hash:
        message_hash = hashlib.sha256(base64.b64decode(boc)).hexdigest()
    return SignerResponse(
        external_message_hash=message_hash,
        seqno=seqno,
        broadcasted=True,
        signer_mode="remote_real",
        raw_result={"mode": "real", "broadcast": True, "toncenter": result},
    )
