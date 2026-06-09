"""request-level ingestion feeds"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Move ingestion feeds to request-level catalog metadata."""

    op.add_column("series_sources", sa.Column("ref_url", sa.String(), nullable=True))
    op.execute("ALTER TABLE series_sources DROP CONSTRAINT IF EXISTS uq_series_sources_catalog_external_code")
    op.alter_column("series_sources", "external_code", existing_type=sa.String(), nullable=True)

    op.drop_constraint("ingestion_feeds_series_source_id_fkey", "ingestion_feeds", type_="foreignkey")
    op.drop_column("ingestion_feeds", "series_source_id")

    op.create_table(
        "ingestion_feed_members",
        sa.Column("ingestion_feed_id", sa.UUID(), nullable=False),
        sa.Column("series_source_id", sa.UUID(), nullable=False),
        sa.Column("selector_type", sa.String(), nullable=False),
        sa.Column("selector_config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("execution_order", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("uuidv7()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["ingestion_feed_id"], ["ingestion_feeds.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["series_source_id"], ["series_sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("series_source_id", name="uq_ingestion_feed_members_series_source_id"),
    )


def downgrade() -> None:
    """Restore source-centric ingestion feeds."""

    op.add_column("ingestion_feeds", sa.Column("series_source_id", sa.UUID(), nullable=True))
    op.execute(
        """
        UPDATE ingestion_feeds AS feed
        SET series_source_id = member.series_source_id
        FROM (
            SELECT DISTINCT ON (ingestion_feed_id)
                ingestion_feed_id,
                series_source_id
            FROM ingestion_feed_members
            ORDER BY ingestion_feed_id, execution_order NULLS LAST, created_at, id
        ) AS member
        WHERE member.ingestion_feed_id = feed.id
        """,
    )
    op.alter_column("ingestion_feeds", "series_source_id", existing_type=sa.UUID(), nullable=False)
    op.create_foreign_key(
        "ingestion_feeds_series_source_id_fkey",
        "ingestion_feeds",
        "series_sources",
        ["series_source_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_table("ingestion_feed_members")
    op.alter_column("series_sources", "external_code", existing_type=sa.String(), nullable=False)
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = 'uq_series_sources_catalog_external_code'
            ) THEN
                ALTER TABLE series_sources
                ADD CONSTRAINT uq_series_sources_catalog_external_code
                UNIQUE (provider_catalog_id, external_code);
            END IF;
        END
        $$;
        """,
    )
    op.drop_column("series_sources", "ref_url")
