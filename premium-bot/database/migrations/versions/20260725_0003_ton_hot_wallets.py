"""add TON hot-wallet risk tables

Revision ID: 20260725_0003
Revises: 20260724_0002
Create Date: 2026-07-25
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260725_0003"
down_revision: str | None = "20260724_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hot_wallets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("wallet_code", sa.String(32), nullable=False),
        sa.Column("address", sa.String(128), nullable=False),
        sa.Column("wallet_version", sa.String(32), nullable=False, server_default="v4r2"),
        sa.Column("status", sa.String(24), nullable=False, server_default="ACTIVE"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("balance_nano", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("reserved_nano", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("single_limit_nano", sa.BigInteger(), nullable=False),
        sa.Column("daily_limit_nano", sa.BigInteger(), nullable=False),
        sa.Column("daily_spent_nano", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("spent_date", sa.Date(), nullable=True),
        sa.Column("minimum_balance_nano", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("target_balance_nano", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("maximum_balance_nano", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("consecutive_failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_seqno", sa.BigInteger(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("wallet_code"),
        sa.UniqueConstraint("address"),
    )
    op.create_index("ix_hot_wallets_wallet_code", "hot_wallets", ["wallet_code"])
    op.create_index("ix_hot_wallets_address", "hot_wallets", ["address"])
    op.create_index("ix_hot_wallets_status", "hot_wallets", ["status"])
    op.create_index("ix_hot_wallets_spent_date", "hot_wallets", ["spent_date"])

    op.create_table(
        "wallet_reservations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("wallet_id", sa.String(36), sa.ForeignKey("hot_wallets.id"), nullable=False),
        sa.Column("reserved_nano", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="RESERVED"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id"),
    )
    op.create_index("ix_wallet_reservations_order_id", "wallet_reservations", ["order_id"])
    op.create_index("ix_wallet_reservations_wallet_id", "wallet_reservations", ["wallet_id"])
    op.create_index("ix_wallet_reservations_status", "wallet_reservations", ["status"])
    op.create_index("ix_wallet_reservations_expires_at", "wallet_reservations", ["expires_at"])
    op.create_index(
        "ix_wallet_reservation_wallet_status", "wallet_reservations", ["wallet_id", "status"]
    )

    op.create_table(
        "ton_transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("wallet_id", sa.String(36), sa.ForeignKey("hot_wallets.id"), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("seqno", sa.BigInteger(), nullable=True),
        sa.Column("valid_until", sa.BigInteger(), nullable=True),
        sa.Column("destination", sa.String(128), nullable=False),
        sa.Column("amount_nano", sa.BigInteger(), nullable=False),
        sa.Column("payload_hash", sa.String(128), nullable=True),
        sa.Column("external_message_hash", sa.String(128), nullable=True),
        sa.Column("tx_hash", sa.String(128), nullable=True),
        sa.Column("tx_lt", sa.String(64), nullable=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="CREATED"),
        sa.Column("broadcast_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_chain_result", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("request_id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("wallet_id", "seqno", name="uq_ton_wallet_seqno"),
    )
    for col in ("order_id", "wallet_id", "request_id", "idempotency_key", "destination", "external_message_hash", "tx_hash", "status"):
        op.create_index(f"ix_ton_transactions_{col}", "ton_transactions", [col])

    op.create_table(
        "payment_whitelist",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("destination", sa.String(128), nullable=False),
        sa.Column("label", sa.String(128), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("maximum_single_nano", sa.BigInteger(), nullable=True),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("destination"),
    )
    op.create_index("ix_payment_whitelist_destination", "payment_whitelist", ["destination"])

    op.create_table(
        "circuit_breakers",
        sa.Column("breaker_key", sa.String(64), primary_key=True),
        sa.Column("state", sa.String(16), nullable=False, server_default="CLOSED"),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_circuit_breakers_state", "circuit_breakers", ["state"])


def downgrade() -> None:
    op.drop_table("circuit_breakers")
    op.drop_table("payment_whitelist")
    op.drop_table("ton_transactions")
    op.drop_table("wallet_reservations")
    op.drop_table("hot_wallets")
