"""Stage 4.1 order fulfillment state and retry metadata.

Revision ID: 20260725_0007
Revises: 20260725_0006
"""
from alembic import op
import sqlalchemy as sa

revision = "20260725_0007"
down_revision = "20260725_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("fulfillment_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("orders", sa.Column("last_fulfillment_error", sa.Text(), nullable=True))
    op.add_column("orders", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("manual_review_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_orders_next_retry_at", "orders", ["next_retry_at"])
    op.create_index("ix_orders_manual_review_at", "orders", ["manual_review_at"])
    op.execute("UPDATE orders SET status='COMPLETED' WHERE status='SUCCESS'")


def downgrade() -> None:
    op.execute("UPDATE orders SET status='SUCCESS' WHERE status='COMPLETED'")
    op.drop_index("ix_orders_manual_review_at", table_name="orders")
    op.drop_index("ix_orders_next_retry_at", table_name="orders")
    op.drop_column("orders", "manual_review_at")
    op.drop_column("orders", "next_retry_at")
    op.drop_column("orders", "last_fulfillment_error")
    op.drop_column("orders", "fulfillment_attempts")
