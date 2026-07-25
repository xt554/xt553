"""Add user USDT wallet, deposits and immutable ledger.

Revision ID: 20260724_0002
Revises: 20260724_0001
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260724_0002"
down_revision: str | None = "20260724_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "user_wallets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("currency", sa.String(16), server_default="USDT", nullable=False),
        sa.Column(
            "available_balance",
            sa.Numeric(18, 6),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "total_deposited",
            sa.Numeric(18, 6),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "total_spent",
            sa.Numeric(18, 6),
            server_default="0",
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        *timestamps(),
        sa.UniqueConstraint(
            "user_id",
            "currency",
            name="uq_user_wallet_currency",
        ),
    )
    op.create_index("ix_user_wallets_user_id", "user_wallets", ["user_id"])

    op.execute(
        sa.text(
            """
            INSERT INTO user_wallets
                (id, user_id, currency, available_balance, total_deposited,
                 total_spent, version, created_at, updated_at)
            SELECT UUID(), id, 'USDT', 0, 0, 0, 1, CURRENT_TIMESTAMP,
                   CURRENT_TIMESTAMP
            FROM users
            """
        )
    )

    op.create_table(
        "wallet_ledger_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "wallet_id",
            sa.String(36),
            sa.ForeignKey("user_wallets.id"),
            nullable=False,
        ),
        sa.Column("entry_type", sa.String(32), nullable=False),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("balance_after", sa.Numeric(18, 6), nullable=False),
        sa.Column("reference_type", sa.String(32), nullable=False),
        sa.Column("reference_id", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_wallet_ledger_entries_wallet_id",
        "wallet_ledger_entries",
        ["wallet_id"],
    )
    op.create_index(
        "ix_wallet_ledger_entries_entry_type",
        "wallet_ledger_entries",
        ["entry_type"],
    )
    op.create_index(
        "ix_wallet_ledger_entries_reference_type",
        "wallet_ledger_entries",
        ["reference_type"],
    )
    op.create_index(
        "ix_wallet_ledger_entries_reference_id",
        "wallet_ledger_entries",
        ["reference_id"],
    )
    op.create_index(
        "ix_wallet_ledger_entries_idempotency_key",
        "wallet_ledger_entries",
        ["idempotency_key"],
    )
    op.create_index(
        "ix_wallet_ledger_entries_created_at",
        "wallet_ledger_entries",
        ["created_at"],
    )
    op.create_index(
        "ix_wallet_ledger_wallet_created",
        "wallet_ledger_entries",
        ["wallet_id", "created_at"],
    )

    op.create_table(
        "deposit_orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("deposit_no", sa.String(32), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "user_wallet_id",
            sa.String(36),
            sa.ForeignKey("user_wallets.id"),
            nullable=False,
        ),
        sa.Column(
            "receive_wallet_id",
            sa.String(36),
            sa.ForeignKey("wallets.id"),
            nullable=False,
        ),
        sa.Column("network", sa.String(16), nullable=False),
        sa.Column("currency", sa.String(16), server_default="USDT", nullable=False),
        sa.Column("requested_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("payment_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("payment_address", sa.String(128), nullable=False),
        sa.Column(
            "status",
            sa.String(24),
            server_default="WAIT_PAY",
            nullable=False,
        ),
        sa.Column("tx_hash", sa.String(128), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.UniqueConstraint("deposit_no"),
    )
    for name in (
        "deposit_no",
        "user_id",
        "user_wallet_id",
        "receive_wallet_id",
        "network",
        "payment_address",
        "status",
        "tx_hash",
        "expires_at",
    ):
        op.create_index(f"ix_deposit_orders_{name}", "deposit_orders", [name])
    op.create_index(
        "ix_deposit_payment_match",
        "deposit_orders",
        ["network", "payment_address", "payment_amount", "status"],
    )

    op.add_column(
        "orders",
        sa.Column(
            "payment_method",
            sa.String(24),
            server_default="ONCHAIN",
            nullable=False,
        ),
    )
    op.add_column(
        "orders",
        sa.Column(
            "balance_payment_attempt",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )
    op.add_column(
        "orders",
        sa.Column(
            "balance_refunded_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index("ix_orders_payment_method", "orders", ["payment_method"])

    op.add_column(
        "payment_transactions",
        sa.Column("deposit_order_id", sa.String(36), nullable=True),
    )
    op.create_foreign_key(
        "fk_payment_transactions_deposit_order_id",
        "payment_transactions",
        "deposit_orders",
        ["deposit_order_id"],
        ["id"],
    )
    op.create_index(
        "ix_payment_transactions_deposit_order_id",
        "payment_transactions",
        ["deposit_order_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payment_transactions_deposit_order_id",
        table_name="payment_transactions",
    )
    op.drop_constraint(
        "fk_payment_transactions_deposit_order_id",
        "payment_transactions",
        type_="foreignkey",
    )
    op.drop_column("payment_transactions", "deposit_order_id")

    op.drop_index("ix_orders_payment_method", table_name="orders")
    op.drop_column("orders", "balance_refunded_at")
    op.drop_column("orders", "balance_payment_attempt")
    op.drop_column("orders", "payment_method")

    op.drop_table("deposit_orders")
    op.drop_table("wallet_ledger_entries")
    op.drop_table("user_wallets")
