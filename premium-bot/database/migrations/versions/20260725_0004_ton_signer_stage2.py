"""harden TON signer and capture metadata

Revision ID: 20260725_0004
Revises: 20260725_0003
Create Date: 2026-07-25
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260725_0004"
down_revision: str | None = "20260725_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ton_transactions", sa.Column("source_address", sa.String(128), nullable=True))
    op.add_column(
        "ton_transactions", sa.Column("capture_fingerprint", sa.String(128), nullable=True)
    )
    op.add_column("ton_transactions", sa.Column("signer_request_id", sa.String(64), nullable=True))
    op.add_column("ton_transactions", sa.Column("signer_mode", sa.String(32), nullable=True))
    op.add_column(
        "ton_transactions",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("ton_transactions", sa.Column("last_error", sa.String(500), nullable=True))
    op.create_index(
        "ix_ton_transactions_source_address", "ton_transactions", ["source_address"]
    )
    op.create_index(
        "ix_ton_transactions_capture_fingerprint", "ton_transactions", ["capture_fingerprint"]
    )
    op.create_index(
        "ix_ton_transactions_signer_request_id",
        "ton_transactions",
        ["signer_request_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_ton_transactions_signer_request_id", table_name="ton_transactions")
    op.drop_index("ix_ton_transactions_capture_fingerprint", table_name="ton_transactions")
    op.drop_index("ix_ton_transactions_source_address", table_name="ton_transactions")
    op.drop_column("ton_transactions", "last_error")
    op.drop_column("ton_transactions", "attempt_count")
    op.drop_column("ton_transactions", "signer_mode")
    op.drop_column("ton_transactions", "signer_request_id")
    op.drop_column("ton_transactions", "capture_fingerprint")
    op.drop_column("ton_transactions", "source_address")
