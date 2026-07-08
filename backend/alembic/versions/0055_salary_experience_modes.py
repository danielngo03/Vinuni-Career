"""Add structured salary_mode/salary_period/salary_gross_net + experience_mode.

Revision ID: 0055_salary_experience_modes
Revises: 0054_otp_and_onboarding
Create Date: 2026-07-04

Backend contract (B-544/B-545): salary/experience are read as structured modes
instead of being inferred client-side from nullable min/max + a disclosed flag.
This migration adds the columns and backfills existing rows deterministically
from their current min/max/disclosed values so no job goes without a mode.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0055_salary_experience_modes"
down_revision = "0054_otp_and_onboarding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("salary_mode", sa.String(length=20), nullable=True))
    op.add_column(
        "jobs",
        sa.Column(
            "salary_period", sa.String(length=10), nullable=False,
            server_default="monthly",
        ),
    )
    op.add_column(
        "jobs",
        sa.Column(
            "salary_gross_net", sa.String(length=15), nullable=False,
            server_default="unspecified",
        ),
    )
    op.add_column(
        "jobs", sa.Column("experience_mode", sa.String(length=20), nullable=True)
    )

    jobs = sa.table(
        "jobs",
        sa.column("id", sa.Uuid()),
        sa.column("salary_min", sa.Integer()),
        sa.column("salary_max", sa.Integer()),
        sa.column("salary_is_disclosed", sa.Boolean()),
        sa.column("salary_mode", sa.String()),
        sa.column("experience_min_years", sa.SmallInteger()),
        sa.column("experience_max_years", sa.SmallInteger()),
        sa.column("experience_mode", sa.String()),
    )

    # --- salary_mode backfill ---
    op.execute(
        jobs.update()
        .where(
            sa.and_(
                jobs.c.salary_is_disclosed.is_(False),
                jobs.c.salary_min.is_(None),
                jobs.c.salary_max.is_(None),
            )
        )
        .values(salary_mode="negotiable")
    )
    op.execute(
        jobs.update()
        .where(
            sa.and_(
                jobs.c.salary_is_disclosed.is_(False),
                sa.or_(jobs.c.salary_min.isnot(None), jobs.c.salary_max.isnot(None)),
            )
        )
        .values(salary_mode="hidden")
    )
    op.execute(
        jobs.update()
        .where(
            sa.and_(
                jobs.c.salary_is_disclosed.is_(True),
                jobs.c.salary_min.isnot(None),
                jobs.c.salary_max.isnot(None),
                jobs.c.salary_min == jobs.c.salary_max,
            )
        )
        .values(salary_mode="fixed")
    )
    op.execute(
        jobs.update()
        .where(
            sa.and_(
                jobs.c.salary_is_disclosed.is_(True),
                jobs.c.salary_min.isnot(None),
                jobs.c.salary_max.isnot(None),
                jobs.c.salary_min < jobs.c.salary_max,
            )
        )
        .values(salary_mode="range")
    )
    op.execute(
        jobs.update()
        .where(
            sa.and_(
                jobs.c.salary_is_disclosed.is_(True),
                jobs.c.salary_min.isnot(None),
                jobs.c.salary_max.is_(None),
            )
        )
        .values(salary_mode="from")
    )
    op.execute(
        jobs.update()
        .where(
            sa.and_(
                jobs.c.salary_is_disclosed.is_(True),
                jobs.c.salary_min.is_(None),
                jobs.c.salary_max.isnot(None),
            )
        )
        .values(salary_mode="to")
    )
    # Any remaining disclosed row with no min/max at all (edge case: disclosed
    # flag set but no numbers ever entered) falls back to negotiable so every
    # row ends up with a non-null mode.
    op.execute(
        jobs.update()
        .where(sa.and_(jobs.c.salary_mode.is_(None)))
        .values(salary_mode="negotiable")
    )

    # --- experience_mode backfill ---
    op.execute(
        jobs.update()
        .where(
            sa.and_(
                jobs.c.experience_min_years.is_(None),
                jobs.c.experience_max_years.is_(None),
            )
        )
        .values(experience_mode="no_requirement")
    )
    op.execute(
        jobs.update()
        .where(
            sa.and_(
                jobs.c.experience_min_years == 0,
                jobs.c.experience_max_years == 0,
            )
        )
        .values(experience_mode="fresher")
    )
    op.execute(
        jobs.update()
        .where(
            sa.and_(
                jobs.c.experience_min_years.isnot(None),
                jobs.c.experience_max_years.isnot(None),
                jobs.c.experience_min_years < jobs.c.experience_max_years,
            )
        )
        .values(experience_mode="range")
    )
    op.execute(
        jobs.update()
        .where(
            sa.and_(
                jobs.c.experience_min_years.isnot(None),
                jobs.c.experience_max_years.isnot(None),
                jobs.c.experience_min_years == jobs.c.experience_max_years,
                jobs.c.experience_min_years != 0,
            )
        )
        .values(experience_mode="range")
    )
    op.execute(
        jobs.update()
        .where(
            sa.and_(
                jobs.c.experience_min_years.isnot(None),
                jobs.c.experience_max_years.is_(None),
            )
        )
        .values(experience_mode="min")
    )
    op.execute(
        jobs.update()
        .where(
            sa.and_(
                jobs.c.experience_min_years.is_(None),
                jobs.c.experience_max_years.isnot(None),
            )
        )
        .values(experience_mode="max")
    )
    op.execute(
        jobs.update()
        .where(jobs.c.experience_mode.is_(None))
        .values(experience_mode="no_requirement")
    )

    op.alter_column("jobs", "salary_period", server_default=None)
    op.alter_column("jobs", "salary_gross_net", server_default=None)


def downgrade() -> None:
    op.drop_column("jobs", "experience_mode")
    op.drop_column("jobs", "salary_gross_net")
    op.drop_column("jobs", "salary_period")
    op.drop_column("jobs", "salary_mode")
