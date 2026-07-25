"""Stage 4.2 Fragment runner jobs.

Revision ID: 20260725_0008
Revises: 20260725_0007
"""
from alembic import op
import sqlalchemy as sa

revision = "20260725_0008"
down_revision = "20260725_0007"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        "fragment_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="QUEUED"),
        sa.Column("runner_id", sa.String(64)),
        sa.Column("wallet_code", sa.String(32)),
        sa.Column("profile_name", sa.String(64)),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("captured_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("quoted_ton_nano", sa.BigInteger()),
        sa.Column("captured_request", sa.JSON()),
        sa.Column("page_url", sa.String(500)),
        sa.Column("screenshot_path", sa.String(500)),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("order_id", name="uq_fragment_jobs_order_id"),
    )
    for name in ("order_id", "status", "runner_id", "wallet_code", "lease_expires_at"):
        op.create_index(f"ix_fragment_jobs_{name}", "fragment_jobs", [name])

def downgrade() -> None:
    op.drop_table("fragment_jobs")
