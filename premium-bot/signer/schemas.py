from __future__ import annotations

from pydantic import BaseModel, Field


class SignerRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=64)
    order_id: str = Field(min_length=36, max_length=36)
    wallet_code: str = Field(min_length=1, max_length=32)
    source_address: str | None = Field(default=None, max_length=128)
    destination: str = Field(min_length=1, max_length=128)
    amount_nano: int = Field(gt=0)
    payload_boc: str = Field(min_length=1)
    payload_hash: str = Field(min_length=64, max_length=128)
    valid_until: int = Field(gt=0)
    network: str = Field(min_length=1, max_length=16)
    idempotency_key: str = Field(min_length=8, max_length=128)
    expected_amount_nano: int = Field(gt=0)
    schema_hash: str = Field(min_length=64, max_length=64)


class SignerResponse(BaseModel):
    external_message_hash: str
    seqno: int | None = None
    broadcasted: bool
    signer_mode: str
    raw_result: dict[str, object]
