"""add dynamic TON policy and real signer metadata

Revision ID: 20260725_0006
Revises: 20260725_0005
Create Date: 2026-07-25
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260725_0006"
down_revision: str | None = "20260725_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = [
        sa.Column("source_address_raw", sa.String(80), nullable=True),
        sa.Column("destination_raw", sa.String(80), nullable=True),
        sa.Column("quoted_amount_nano", sa.BigInteger(), nullable=True),
        sa.Column("amount_deviation_bps", sa.Integer(), nullable=True),
        sa.Column("payload_boc", sa.Text(), nullable=True),
        sa.Column("payload_opcode", sa.BigInteger(), nullable=True),
        sa.Column("payload_bit_length", sa.Integer(), nullable=True),
        sa.Column("payload_ref_count", sa.Integer(), nullable=True),
        sa.Column("schema_hash", sa.String(128), nullable=True),
        sa.Column("fragment_status", sa.String(24), nullable=True),
        sa.Column("fragment_completed_at", sa.DateTime(timezone=True), nullable=True),
    ]
    for column in columns:
        op.add_column("ton_transactions", column)
    for name in (
        "source_address_raw",
        "destination_raw",
        "schema_hash",
        "fragment_status",
    ):
        op.create_index(f"ix_ton_transactions_{name}", "ton_transactions", [name])

    op.create_table(
        "ton_schema_policies",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("schema_hash", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="PENDING"),
        sa.Column("label", sa.String(128), nullable=True),
        sa.Column("network", sa.String(16), nullable=False, server_default="-239"),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("destination_workchain", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("payload_opcode", sa.BigInteger(), nullable=True),
        sa.Column("payload_bit_length", sa.Integer(), nullable=True),
        sa.Column("payload_ref_count", sa.Integer(), nullable=True),
        sa.Column("has_state_init", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("has_extra_currency", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("schema_hash"),
    )
    op.create_index("ix_ton_schema_policies_schema_hash", "ton_schema_policies", ["schema_hash"])
    op.create_index("ix_ton_schema_policies_status", "ton_schema_policies", ["status"])


def downgrade() -> None:
    op.drop_table("ton_schema_policies")
    for name in (
        "fragment_status",
        "schema_hash",
        "destination_raw",
        "source_address_raw",
    ):
        op.drop_index(f"ix_ton_transactions_{name}", table_name="ton_transactions")
    for name in (
        "fragment_completed_at",
        "fragment_status",
        "schema_hash",
        "payload_ref_count",
        "payload_bit_length",
        "payload_opcode",
        "payload_boc",
        "amount_deviation_bps",
        "quoted_amount_nano",
        "destination_raw",
        "source_address_raw",
    ):
        op.drop_column("ton_transactions", name)
