
"""Stage 4.3 production Fragment runner observability and account rotation.

Revision ID: 20260725_0009
Revises: 20260725_0008
"""
from alembic import op
import sqlalchemy as sa

revision = "20260725_0009"
down_revision = "20260725_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fragment_accounts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("profile_name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(24), nullable=False, server_default="ACTIVE"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("lease_runner_id", sa.String(64)),
        sa.Column("lease_job_id", sa.String(36)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("last_login_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_failure_at", sa.DateTime(timezone=True)),
        sa.Column("cookie_updated_at", sa.DateTime(timezone=True)),
        sa.Column("selector_checked_at", sa.DateTime(timezone=True)),
        sa.Column("selector_status", sa.String(24), nullable=False, server_default="UNKNOWN"),
        sa.Column("last_page_url", sa.String(500)),
        sa.Column("last_error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", name="uq_fragment_accounts_code"),
        sa.UniqueConstraint("profile_name", name="uq_fragment_accounts_profile_name"),
    )
    for name in ("code", "status", "priority", "is_enabled", "lease_runner_id", "lease_job_id", "lease_expires_at", "selector_status"):
        op.create_index(f"ix_fragment_accounts_{name}", "fragment_accounts", [name])

    op.create_table(
        "fragment_runner_instances",
        sa.Column("runner_id", sa.String(64), primary_key=True),
        sa.Column("status", sa.String(24), nullable=False, server_default="STARTING"),
        sa.Column("mode", sa.String(24), nullable=False, server_default="observe"),
        sa.Column("version", sa.String(32), nullable=False, server_default="4.3.0"),
        sa.Column("browser_healthy", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("api_healthy", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("fragment_reachable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("login_status", sa.String(24), nullable=False, server_default="UNKNOWN"),
        sa.Column("selector_status", sa.String(24), nullable=False, server_default="UNKNOWN"),
        sa.Column("current_job_id", sa.String(36)),
        sa.Column("current_account_code", sa.String(64)),
        sa.Column("queue_depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("page_url", sa.String(500)),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_claim_at", sa.DateTime(timezone=True)),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.Text()),
        sa.Column("runtime_metadata", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for name in ("status", "current_job_id", "current_account_code", "last_heartbeat_at"):
        op.create_index(f"ix_fragment_runner_instances_{name}", "fragment_runner_instances", [name])

    with op.batch_alter_table("fragment_jobs") as batch:
        batch.add_column(sa.Column("account_id", sa.String(36), nullable=True))
        batch.add_column(sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="6"))
        batch.add_column(sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("retry_delay_seconds", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("failure_kind", sa.String(64), nullable=True))
        batch.add_column(sa.Column("trace_path", sa.String(500), nullable=True))
        batch.add_column(sa.Column("html_path", sa.String(500), nullable=True))
        batch.add_column(sa.Column("console_path", sa.String(500), nullable=True))
        batch.add_column(sa.Column("selector_snapshot", sa.JSON(), nullable=True))
        batch.alter_column("profile_name", existing_type=sa.String(64), type_=sa.String(128), existing_nullable=True)
        batch.create_foreign_key("fk_fragment_jobs_account_id", "fragment_accounts", ["account_id"], ["id"])
    for name in ("account_id", "next_retry_at", "failure_kind"):
        op.create_index(f"ix_fragment_jobs_{name}", "fragment_jobs", [name])


def downgrade() -> None:
    for name in ("account_id", "next_retry_at", "failure_kind"):
        op.drop_index(f"ix_fragment_jobs_{name}", table_name="fragment_jobs")
    with op.batch_alter_table("fragment_jobs") as batch:
        batch.drop_constraint("fk_fragment_jobs_account_id", type_="foreignkey")
        for name in ("selector_snapshot", "console_path", "html_path", "trace_path", "failure_kind", "retry_delay_seconds", "next_retry_at", "max_attempts", "account_id"):
            batch.drop_column(name)
        batch.alter_column("profile_name", existing_type=sa.String(128), type_=sa.String(64), existing_nullable=True)
    op.drop_table("fragment_runner_instances")
    op.drop_table("fragment_accounts")
