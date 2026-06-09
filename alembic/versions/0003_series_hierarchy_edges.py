"""add series hierarchy edges"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "series_hierarchy_edges",
        sa.Column("parent_series_id", sa.UUID(), nullable=False),
        sa.Column("child_series_id", sa.UUID(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("parent_series_id != child_series_id", name="ck_series_hierarchy_edges_no_self_edge"),
        sa.ForeignKeyConstraint(["child_series_id"], ["series.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_series_id"], ["series.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("parent_series_id", "child_series_id", name="uq_series_hierarchy_edges_parent_child"),
    )


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_table("series_hierarchy_edges")
