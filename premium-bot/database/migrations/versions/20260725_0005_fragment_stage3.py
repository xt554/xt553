"""fragment dynamic policy stage 3

Revision ID: 20260725_0005
Revises: 20260725_0004
"""
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
revision: str = "20260725_0005"
down_revision: str | None = "20260725_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
def upgrade() -> None:
    op.create_table("ton_transaction_schemas",
        sa.Column("schema_hash", sa.String(64), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_destination", sa.String(128)), sa.Column("last_destination", sa.String(128)),
        sa.Column("last_payload_hash", sa.String(128)), sa.Column("approved_by", sa.String(64)),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_ton_transaction_schemas_enabled", "ton_transaction_schemas", ["enabled"])
def downgrade() -> None:
    op.drop_index("ix_ton_transaction_schemas_enabled", table_name="ton_transaction_schemas")
    op.drop_table("ton_transaction_schemas")
