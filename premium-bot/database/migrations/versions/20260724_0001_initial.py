"""Initial premium bot schema.

Revision ID: 20260724_0001
Revises:
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260724_0001"
down_revision: str | None = None
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
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_username", sa.String(64), nullable=True),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.UniqueConstraint("telegram_id"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"])
    op.create_index("ix_users_telegram_username", "users", ["telegram_username"])
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_role", "users", ["role"])

    op.create_table(
        "plans",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("months", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(18, 6), nullable=False),
        sa.Column("currency", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("months"),
    )
    op.create_index("ix_plans_code", "plans", ["code"])
    op.create_index("ix_plans_is_active", "plans", ["is_active"])

    op.create_table(
        "wallets",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("network", sa.String(16), nullable=False),
        sa.Column("address", sa.String(128), nullable=False),
        sa.Column("token_contract", sa.String(128), nullable=True),
        sa.Column("token_decimals", sa.Integer(), nullable=False),
        sa.Column("min_confirmations", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("last_scanned_block", sa.BigInteger(), nullable=True),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
        sa.UniqueConstraint("network", "address", name="uq_wallet_network_address"),
    )
    op.create_index("ix_wallets_network", "wallets", ["network"])
    op.create_index("ix_wallets_address", "wallets", ["address"])
    op.create_index("ix_wallets_is_enabled", "wallets", ["is_enabled"])

    op.create_table(
        "order_sequences",
        sa.Column("sequence_date", sa.Date(), primary_key=True),
        sa.Column("current_value", sa.Integer(), nullable=False),
    )

    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(128), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("updated_by", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        *timestamps(),
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("actor_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(128), nullable=False),
        sa.Column("target_type", sa.String(64), nullable=True),
        sa.Column("target_id", sa.String(64), nullable=True),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_target_type", "audit_logs", ["target_type"])
    op.create_index("ix_audit_logs_target_id", "audit_logs", ["target_id"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    op.create_table(
        "orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_no", sa.String(32), nullable=False),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("plan_id", sa.String(36), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("wallet_id", sa.String(36), sa.ForeignKey("wallets.id"), nullable=True),
        sa.Column("target_username", sa.String(64), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("network", sa.String(16), nullable=False),
        sa.Column("currency", sa.String(16), nullable=False),
        sa.Column("quoted_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("payment_amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("payment_address", sa.String(128), nullable=False),
        sa.Column("tx_hash", sa.String(128), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("premium_reference", sa.String(128), nullable=True),
        sa.Column("callback_url", sa.String(500), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        *timestamps(),
        sa.UniqueConstraint("order_no"),
    )
    op.create_index("ix_orders_order_no", "orders", ["order_no"])
    op.create_index("ix_orders_user_id", "orders", ["user_id"])
    op.create_index("ix_orders_plan_id", "orders", ["plan_id"])
    op.create_index("ix_orders_wallet_id", "orders", ["wallet_id"])
    op.create_index("ix_orders_target_username", "orders", ["target_username"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_network", "orders", ["network"])
    op.create_index("ix_orders_tx_hash", "orders", ["tx_hash"])
    op.create_index("ix_orders_expires_at", "orders", ["expires_at"])
    op.create_index("ix_orders_premium_reference", "orders", ["premium_reference"])
    op.create_index(
        "ix_order_payment_match",
        "orders",
        ["network", "payment_address", "payment_amount", "status"],
    )
    op.create_index("ix_order_user_created", "orders", ["user_id", "created_at"])

    op.create_table(
        "order_status_history",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("from_status", sa.String(24), nullable=True),
        sa.Column("to_status", sa.String(24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_type", sa.String(24), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.create_index("ix_order_status_history_order_id", "order_status_history", ["order_id"])
    op.create_index("ix_order_status_history_to_status", "order_status_history", ["to_status"])
    op.create_index("ix_order_status_history_created_at", "order_status_history", ["created_at"])

    op.create_table(
        "payment_transactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=True),
        sa.Column("network", sa.String(16), nullable=False),
        sa.Column("tx_hash", sa.String(128), nullable=False),
        sa.Column("log_index", sa.Integer(), nullable=False),
        sa.Column("block_number", sa.BigInteger(), nullable=True),
        sa.Column("block_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("from_address", sa.String(128), nullable=True),
        sa.Column("to_address", sa.String(128), nullable=False),
        sa.Column("token_contract", sa.String(128), nullable=True),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("confirmations", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        *timestamps(),
        sa.UniqueConstraint("network", "tx_hash", "log_index", name="uq_chain_transaction"),
    )
    op.create_index("ix_payment_transactions_order_id", "payment_transactions", ["order_id"])
    op.create_index("ix_payment_transactions_network", "payment_transactions", ["network"])
    op.create_index("ix_payment_transactions_tx_hash", "payment_transactions", ["tx_hash"])
    op.create_index("ix_payment_transactions_to_address", "payment_transactions", ["to_address"])
    op.create_index("ix_payment_transactions_status", "payment_transactions", ["status"])

    op.create_table(
        "refunds",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("requested_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("destination_address", sa.String(128), nullable=False),
        sa.Column("network", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("provider_reference", sa.String(128), nullable=True),
        sa.Column("tx_hash", sa.String(128), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        *timestamps(),
    )
    op.create_index("ix_refunds_order_id", "refunds", ["order_id"])
    op.create_index("ix_refunds_requested_by", "refunds", ["requested_by"])
    op.create_index("ix_refunds_status", "refunds", ["status"])

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("target_url", sa.String(500), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        *timestamps(),
    )
    op.create_index("ix_webhook_deliveries_order_id", "webhook_deliveries", ["order_id"])
    op.create_index("ix_webhook_deliveries_event", "webhook_deliveries", ["event"])


def downgrade() -> None:
    op.drop_table("webhook_deliveries")
    op.drop_table("refunds")
    op.drop_table("payment_transactions")
    op.drop_table("order_status_history")
    op.drop_table("orders")
    op.drop_table("audit_logs")
    op.drop_table("system_settings")
    op.drop_table("order_sequences")
    op.drop_table("wallets")
    op.drop_table("plans")
    op.drop_table("users")
