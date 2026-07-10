"""Talent-pool CV embeddings (``cv_embeddings``) — pgvector-free semantic index.

pgvector is NOT installed on this Postgres, so the embedding is stored PORTABLY
as a JSONB list of floats and ranked in Python via
``app.ai.retrieval.embeddings.top_k_by_cosine`` (local scale = hundreds of
consented CVs, so a full in-process cosine scan is fine). This deliberately does
NOT depend on the ``<=>`` pgvector operator or a ``vector`` column type.

One row per (consented, discoverable) CV per embedding model alias — the current
committed CV content is embedded once and reused. ``text_hash`` makes re-indexing
idempotent (skip when the meaningful CV text is unchanged).

Privacy / ownership:
- ``snapshot_id`` is a BARE UUID (the immutable ``cv_versions`` snapshot the
  vector reflects) — no hard FK because the ``documents`` module owns CV
  snapshots (mirrors ``cv_evaluations.snapshot_id``). ``cv_id`` / ``user_id`` FK
  the owning rows with ``ON DELETE CASCADE`` so a deleted CV / user never leaves a
  dangling vector.
- ``content_text`` is a capped, derived matching projection of the student's OWN
  consented CV (like ``cv_profiles.matching_json``). It powers the deterministic
  keyword+skill fallback when AI is off; it is NEVER surfaced raw to a partner —
  only human-readable match reasons are.
- No provider/model/token/embedding-dim internals are stored beyond the masked
  ``model_alias`` (already used across the AI ledger).

Consent gate (owner follow-up): there is no dedicated ``talent_pool_opt_in`` flag
yet, so indexing/searching gates on the existing discoverability signals
(``is_open_to_work`` + ``profile_visibility``). A first-class opt-in column is a
recommended follow-up migration (see the service docstring).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0097_cv_embeddings"
down_revision: str | None = "0096_cv_evaluation_cache"
branch_labels: str | None = None
depends_on: str | None = None

_UUID = postgresql.UUID(as_uuid=True)
_UUID_DEFAULT = sa.text("gen_random_uuid()")


def upgrade() -> None:
    op.create_table(
        "cv_embeddings",
        sa.Column("id", _UUID, primary_key=True, server_default=_UUID_DEFAULT),
        # The immutable CV version snapshot this vector reflects (documents-owned;
        # bare UUID, no hard FK — mirrors cv_evaluations.snapshot_id).
        sa.Column("snapshot_id", _UUID, nullable=False),
        # The owning CV + user (cascade cleanup on delete).
        sa.Column(
            "cv_id",
            _UUID,
            sa.ForeignKey("cv_profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            _UUID,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Masked embedding model alias (never the concrete model id).
        sa.Column("model_alias", sa.String(80), nullable=False),
        # CV content version the vector reflects (freshness stamp).
        sa.Column("content_version", sa.Integer(), nullable=False, server_default="1"),
        # PORTABLE embedding vector: a JSONB list of floats ranked in Python.
        sa.Column(
            "vector",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        # Lowercased skill names for deterministic skill filtering.
        sa.Column(
            "skills",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        # Coarse years-of-experience estimate for the min_experience filter.
        sa.Column("experience_years", sa.SmallInteger(), nullable=True),
        # Capped derived matching text (deterministic keyword fallback; never
        # surfaced raw to a partner).
        sa.Column("content_text", sa.Text(), nullable=False, server_default=""),
        # sha256 of content_text — re-index idempotency (skip when unchanged).
        sa.Column("text_hash", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        # One current vector per CV-content snapshot per embedding model.
        sa.UniqueConstraint(
            "snapshot_id", "model_alias", name="uq_cv_embeddings_snapshot_model"
        ),
    )
    op.create_index("ix_cv_embeddings_user", "cv_embeddings", ["user_id"])
    op.create_index("ix_cv_embeddings_cv", "cv_embeddings", ["cv_id"])


def downgrade() -> None:
    op.drop_index("ix_cv_embeddings_cv", table_name="cv_embeddings")
    op.drop_index("ix_cv_embeddings_user", table_name="cv_embeddings")
    op.drop_table("cv_embeddings")
