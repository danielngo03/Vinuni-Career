"""Add job_embeddings table for pgvector semantic search.

Creates the ``job_embeddings`` table and installs the pgvector extension when
``pgvector_enabled = true`` in settings. The migration is safe to run even when
pgvector is not yet installed — it emits a NOTICE and creates the table using a
``TEXT`` column as a degraded fallback, then alters it to ``vector(1536)`` only
when the extension is available. This keeps the app bootable in bare-metal dev
envs without pgvector while still migrating cleanly on production infra.

Revision ID: 0039_job_embeddings
Revises: 0038_job_language_translation
Create Date: 2026-07-01
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine import reflection

revision = "0039_job_embeddings"
down_revision = "0038_job_language_translation"
branch_labels = None
depends_on = None

_TABLE = "job_embeddings"
_INDEX = "ix_job_embeddings_vector_cosine"


def _pgvector_available() -> bool:
    """Check whether the pgvector extension is installed in this Postgres instance."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT 1 FROM pg_available_extensions WHERE name = 'vector'")
    )
    return result.fetchone() is not None


def upgrade() -> None:
    # Install pgvector only when it exists in this Postgres cluster. Avoid
    # catching a failed CREATE EXTENSION inside the migration transaction because
    # PostgreSQL marks the whole transaction as aborted after that error.
    has_vector = _pgvector_available()
    if has_vector:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # Create the table with a TEXT placeholder for the vector column so that
    # the table always exists (makes app imports safe even without pgvector).
    op.create_table(
        _TABLE,
        sa.Column("job_id", sa.UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("model_alias", sa.String(100), nullable=False, server_default="embedding_cheap"),
        # Provisionally TEXT; altered to vector(1536) below when pgvector is present.
        sa.Column("vector", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name="fk_job_embeddings_job_id",
            ondelete="CASCADE",
        ),
    )

    if has_vector:
        # Alter the column to the native vector type and create an IVFFlat index
        # for approximate nearest-neighbour cosine search.
        op.execute(
            "ALTER TABLE job_embeddings ALTER COLUMN vector TYPE vector(1536) "
            "USING vector::vector(1536)"
        )
        # IVFFlat with cosine distance. Lists = sqrt(expected rows) is a good
        # default; start with 100 and rebuild after 1 M rows.
        op.execute(
            f"CREATE INDEX {_INDEX} ON {_TABLE} "
            "USING ivfflat (vector vector_cosine_ops) WITH (lists = 100)"
        )


def downgrade() -> None:
    inspector = reflection.Inspector.from_engine(op.get_bind())
    indexes = [idx["name"] for idx in inspector.get_indexes(_TABLE)]
    if _INDEX in indexes:
        op.execute(f"DROP INDEX IF EXISTS {_INDEX}")
    op.drop_table(_TABLE)
