"""ingestion run-log member outcomes"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add member-level outcomes for shared-request ingestion runs."""

    op.create_table(
        "ingestion_run_log_members",
        sa.Column("ingestion_run_log_id", sa.UUID(), nullable=False),
        sa.Column("ingestion_feed_member_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "success",
                "failed",
                "partial",
                name="ck_ingestion_run_log_members_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("rows_fetched", sa.Integer(), nullable=True),
        sa.Column("rows_inserted", sa.Integer(), nullable=True),
        sa.Column("rows_skipped", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("diagnostics", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["ingestion_feed_member_id"], ["ingestion_feed_members.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ingestion_run_log_id"], ["ingestion_run_logs.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "ingestion_run_log_id",
            "ingestion_feed_member_id",
            name="uq_ingestion_run_log_members_run_member",
        ),
    )


def downgrade() -> None:
    """Remove member-level ingestion run outcomes."""

    op.drop_table("ingestion_run_log_members")
