"""phase 3c: interview intelligence agent tables

Revision ID: 0005_interview_intel
Revises: 0004_apply_sessions
Create Date: 2026-06-08 19:30:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_interview_intel"
down_revision: str | Sequence[str] | None = "0004_apply_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -------------------- interview_plans --------------------
    op.create_table(
        "interview_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("stages", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "technical_topics",
            sa.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "behavioral_topics",
            sa.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "company_prep",
            sa.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("difficulty", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("confidence_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("risk_areas", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column(
            "strengths",
            sa.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_interview_plans_generated_at", "interview_plans", ["generated_at"]
    )

    # -------------------- interview_questions --------------------
    op.create_table(
        "interview_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "plan_id",
            sa.Integer(),
            sa.ForeignKey("interview_plans.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("category", sa.String(32), nullable=False, index=True),
        sa.Column("topic", sa.String(128), nullable=False),
        sa.Column("difficulty", sa.String(16), nullable=False, index=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("answer_outline", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # -------------------- interview_study_plans --------------------
    op.create_table(
        "interview_study_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "plan_id",
            sa.Integer(),
            sa.ForeignKey("interview_plans.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("horizon_days", sa.Integer(), nullable=False, index=True),
        sa.Column("blocks", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("total_hours", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "plan_id", "horizon_days", name="uq_interview_study_plans_plan_horizon"
        ),
    )


def downgrade() -> None:
    op.drop_table("interview_study_plans")
    op.drop_table("interview_questions")
    op.drop_index("ix_interview_plans_generated_at", table_name="interview_plans")
    op.drop_table("interview_plans")
