"""langgraph checkpoint schema"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


LANGGRAPH_TABLES = (
    "checkpoint_migrations",
    "checkpoints",
    "checkpoint_blobs",
    "checkpoint_writes",
)


def upgrade() -> None:
    """Create the isolated LangGraph checkpoint schema."""

    op.execute("CREATE SCHEMA IF NOT EXISTS langgraph AUTHORIZATION macrodb_owner")
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS langgraph.checkpoint_migrations (
            v INTEGER PRIMARY KEY
        )
        """,
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS langgraph.checkpoints (
            thread_id TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            checkpoint_id TEXT NOT NULL,
            parent_checkpoint_id TEXT,
            type TEXT,
            checkpoint JSONB NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}',
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
        )
        """,
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS langgraph.checkpoint_blobs (
            thread_id TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            channel TEXT NOT NULL,
            version TEXT NOT NULL,
            type TEXT NOT NULL,
            blob BYTEA,
            PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
        )
        """,
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS langgraph.checkpoint_writes (
            thread_id TEXT NOT NULL,
            checkpoint_ns TEXT NOT NULL DEFAULT '',
            checkpoint_id TEXT NOT NULL,
            task_id TEXT NOT NULL,
            idx INTEGER NOT NULL,
            channel TEXT NOT NULL,
            type TEXT,
            blob BYTEA NOT NULL,
            task_path TEXT NOT NULL DEFAULT '',
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
        )
        """,
    )
    op.create_index(
        "checkpoints_thread_id_idx",
        "checkpoints",
        ["thread_id"],
        schema="langgraph",
        if_not_exists=True,
    )
    op.create_index(
        "checkpoint_blobs_thread_id_idx",
        "checkpoint_blobs",
        ["thread_id"],
        schema="langgraph",
        if_not_exists=True,
    )
    op.create_index(
        "checkpoint_writes_thread_id_idx",
        "checkpoint_writes",
        ["thread_id"],
        schema="langgraph",
        if_not_exists=True,
    )
    op.execute(
        """
        INSERT INTO langgraph.checkpoint_migrations (v)
        SELECT generate_series(0, 9)
        ON CONFLICT (v) DO NOTHING
        """,
    )
    op.execute("GRANT USAGE ON SCHEMA langgraph TO macrodb_app")
    op.execute(
        """
        GRANT SELECT, INSERT, UPDATE, DELETE
        ON ALL TABLES IN SCHEMA langgraph
        TO macrodb_app
        """,
    )


def downgrade() -> None:
    """Drop the LangGraph checkpoint schema."""

    op.execute("DROP SCHEMA IF EXISTS langgraph CASCADE")
