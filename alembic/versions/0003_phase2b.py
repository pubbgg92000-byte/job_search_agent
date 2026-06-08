"""phase 2b: career-os tables + applications extension

Revision ID: 0003_phase2b
Revises: 0002_discovery
Create Date: 2026-06-08 14:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_phase2b"
down_revision: str | Sequence[str] | None = "0002_discovery"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # -------------------- user_preferences --------------------
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "preferred_locations",
            sa.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("remote_only", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.String(8), nullable=True),
        sa.Column(
            "preferred_roles",
            sa.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "preferred_skills",
            sa.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "excluded_companies",
            sa.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "excluded_keywords",
            sa.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    # -------------------- company_profiles --------------------
    op.create_table(
        "company_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("website", sa.String(2048), nullable=True),
        sa.Column("industry", sa.String(128), nullable=True),
        sa.Column("company_size", sa.String(32), nullable=True),
        sa.Column("funding_stage", sa.String(32), nullable=True),
        sa.Column("remote_policy", sa.String(32), nullable=True),
        sa.Column("growth_score", sa.Integer(), nullable=True),
        sa.Column("risk_score", sa.Integer(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("apply_recommendation", sa.Boolean(), nullable=True),
        sa.Column("raw_signals", sa.JSON(), nullable=True),
        sa.Column(
            "last_updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # -------------------- applications extension --------------------
    # Phase 1 created `applications(user_id, job_id NOT NULL, artifact_id NOT NULL, ...)`.
    # Phase 2B applications can stand alone (Saved status, no tailoring yet) and can be
    # tied to a discovered job. Loosen the NOT NULL constraints and add the new columns.
    op.alter_column("applications", "job_id", nullable=True)
    op.alter_column("applications", "artifact_id", nullable=True)
    op.add_column(
        "applications",
        sa.Column(
            "discovered_job_id",
            sa.Integer(),
            sa.ForeignKey("discovered_jobs.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    op.add_column("applications", sa.Column("company", sa.String(255), nullable=True))
    op.add_column("applications", sa.Column("title", sa.String(512), nullable=True))
    op.add_column("applications", sa.Column("url", sa.String(2048), nullable=True))
    op.add_column(
        "applications",
        sa.Column("source", sa.String(64), nullable=True),
    )
    op.add_column(
        "applications",
        sa.Column("recruiter_name", sa.String(255), nullable=True),
    )
    op.add_column(
        "applications",
        sa.Column("recruiter_email", sa.String(255), nullable=True),
    )
    op.add_column(
        "applications",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # -------------------- application_events --------------------
    # Immutable log: every status transition or note becomes an event.
    op.create_table(
        "application_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=True),
        sa.Column("to_status", sa.String(32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_application_events_occurred_at", "application_events", ["occurred_at"]
    )

    # -------------------- interviews --------------------
    op.create_table(
        "interviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("round_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("kind", sa.String(64), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("interviewer", sa.String(255), nullable=True),
        sa.Column("outcome", sa.String(32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # -------------------- offers --------------------
    op.create_table(
        "offers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("base_salary", sa.Integer(), nullable=True),
        sa.Column("bonus", sa.Integer(), nullable=True),
        sa.Column("equity", sa.String(255), nullable=True),
        sa.Column("currency", sa.String(8), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision", sa.String(32), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # -------------------- skill_gap_snapshots --------------------
    # Persisted per generation so we can chart trends and replay old reports.
    op.create_table(
        "skill_gap_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("jobs_considered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gaps_json", sa.JSON(), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("skill_gap_snapshots")
    op.drop_table("offers")
    op.drop_table("interviews")
    op.drop_index(
        "ix_application_events_occurred_at", table_name="application_events"
    )
    op.drop_table("application_events")

    for col in (
        "created_at",
        "recruiter_email",
        "recruiter_name",
        "source",
        "url",
        "title",
        "company",
        "discovered_job_id",
    ):
        op.drop_column("applications", col)
    op.alter_column("applications", "artifact_id", nullable=False)
    op.alter_column("applications", "job_id", nullable=False)

    op.drop_table("company_profiles")
    op.drop_table("user_preferences")
