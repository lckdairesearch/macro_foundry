"""move observation provenance to member run outcomes"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Move ingested observations from feed-level to member-level provenance."""

    op.add_column("observations", sa.Column("ingestion_run_log_member_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "observations_ingestion_run_log_member_id_fkey",
        "observations",
        "ingestion_run_log_members",
        ["ingestion_run_log_member_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        """
        WITH single_member_runs AS (
            SELECT ingestion_run_log_id, (array_agg(id))[1] AS member_log_id
            FROM ingestion_run_log_members
            GROUP BY ingestion_run_log_id
            HAVING count(*) = 1
        )
        UPDATE observations AS obs
        SET ingestion_run_log_member_id = single_member_runs.member_log_id
        FROM single_member_runs
        WHERE obs.ingestion_run_log_id = single_member_runs.ingestion_run_log_id
        """,
    )
    op.execute("DROP VIEW IF EXISTS latest_observations")
    op.drop_constraint("observations_ingestion_run_log_id_fkey", "observations", type_="foreignkey")
    op.drop_column("observations", "ingestion_run_log_id")
    op.execute(
        """
        CREATE VIEW latest_observations AS
        SELECT DISTINCT ON (series_id, period_start) *
        FROM observations
        ORDER BY series_id, period_start, vintage_date DESC
        """,
    )


def downgrade() -> None:
    """Restore feed-level observation provenance."""

    op.add_column("observations", sa.Column("ingestion_run_log_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "observations_ingestion_run_log_id_fkey",
        "observations",
        "ingestion_run_logs",
        ["ingestion_run_log_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.execute(
        """
        UPDATE observations AS obs
        SET ingestion_run_log_id = member.ingestion_run_log_id
        FROM ingestion_run_log_members AS member
        WHERE obs.ingestion_run_log_member_id = member.id
        """,
    )
    op.execute("DROP VIEW IF EXISTS latest_observations")
    op.drop_constraint("observations_ingestion_run_log_member_id_fkey", "observations", type_="foreignkey")
    op.drop_column("observations", "ingestion_run_log_member_id")
    op.execute(
        """
        CREATE VIEW latest_observations AS
        SELECT DISTINCT ON (series_id, period_start) *
        FROM observations
        ORDER BY series_id, period_start, vintage_date DESC
        """,
    )
