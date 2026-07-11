"""Persisted on-demand HR CV↔JD evaluation cache (``cv_evaluations``).

The partner "AI evaluate this candidate" action (recruitment) produces a
version-stamped verdict for one application's IMMUTABLE CV snapshot against the
job it was submitted to. Persisting it means re-opening the modal returns the
stored verdict instantly (no re-spend); ``?refresh=true`` recomputes and
re-meters. A row is invalidated (recomputed in place) when the JD changes
(``job_version`` stamp) — the CV side is immutable via ``snapshot_id``, so
``snapshot_id`` IS the CV-content version.

The stored ``result_json`` is the user-safe verdict only (recommendation /
summary / strengths / gaps / criteria) — never provider/model/token/latency/
prompt internals (enforced by the service + output guard).

Cross-module note: ``snapshot_id`` is a bare UUID (no FK) because the immutable
snapshot is owned by the ``documents`` module; ``application_id`` / ``job_id`` /
``org_id`` FK the recruitment-visible tables with ``ON DELETE CASCADE`` so a
deleted application / job / org never leaves a dangling verdict.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0096_cv_evaluation_cache"
down_revision: str | None = "0095_remove_anonymous_apply_reveal"
branch_labels: str | None = None
depends_on: str | None = None

_UUID = postgresql.UUID(as_uuid=True)
_UUID_DEFAULT = sa.text("gen_random_uuid()")


def upgrade() -> None:
    op.create_table(
        "cv_evaluations",
        sa.Column("id", _UUID, primary_key=True, server_default=_UUID_DEFAULT),
        sa.Column(
            "application_id",
            _UUID,
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Bare UUID (documents owns the snapshot) — indexed for the cache lookup.
        sa.Column("snapshot_id", _UUID, nullable=False),
        sa.Column(
            "job_id", _UUID, sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "org_id",
            _UUID,
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Content-version stamps: CV side is immutable (snapshot_id), so cv_version
        # is a stable stamp (reserved for a future re-snapshot scheme); job_version
        # drives JD-edit invalidation (recompute-in-place when it changes).
        sa.Column("cv_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("job_version", sa.Integer(), nullable=False, server_default="1"),
        # Verdict headline (categorical) + optional secondary numeric.
        sa.Column("recommendation", sa.String(20), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=True),
        # The deterministic match score used to ground / fall back the verdict.
        sa.Column("deterministic_score", sa.Integer(), nullable=True),
        # User-safe structured verdict payload (no provider/model/token internals).
        sa.Column(
            "result_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "is_fallback", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column(
            "created_by",
            _UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
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
        # One cached verdict per (candidate CV snapshot, job, cv content version).
        sa.UniqueConstraint(
            "snapshot_id", "job_id", "cv_version", name="uq_cv_evaluations_snapshot_job"
        ),
    )
    op.create_index(
        "ix_cv_evaluations_application", "cv_evaluations", ["application_id"]
    )
    op.create_index("ix_cv_evaluations_snapshot", "cv_evaluations", ["snapshot_id"])
    op.create_index("ix_cv_evaluations_job", "cv_evaluations", ["job_id"])
    op.create_index("ix_cv_evaluations_org", "cv_evaluations", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_cv_evaluations_org", table_name="cv_evaluations")
    op.drop_index("ix_cv_evaluations_job", table_name="cv_evaluations")
    op.drop_index("ix_cv_evaluations_snapshot", table_name="cv_evaluations")
    op.drop_index("ix_cv_evaluations_application", table_name="cv_evaluations")
    op.drop_table("cv_evaluations")
