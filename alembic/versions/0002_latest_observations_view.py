"""latest_observations view"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create the latest_observations view."""

    op.execute(
        """
        CREATE VIEW latest_observations AS
        SELECT DISTINCT ON (series_id, period_start) *
        FROM observations
        ORDER BY series_id, period_start, vintage_date DESC
        """
    )


def downgrade() -> None:
    """Drop the latest_observations view."""

    op.execute("DROP VIEW IF EXISTS latest_observations")
