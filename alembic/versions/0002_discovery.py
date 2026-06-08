"""phase 2: discovery tables

Revision ID: 0002_discovery
Revises: 0001_initial
Create Date: 2026-06-08 13:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_discovery"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("slug", sa.String(255), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("config_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("kind", "slug", name="uq_job_sources_kind_slug"),
    )

    op.create_table(
        "discovered_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False, index=True),
        sa.Column("source_job_id", sa.String(255), nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("job_sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("company", sa.String(255), nullable=False),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column("remote", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.String(8), nullable=True),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source", "source_job_id", name="uq_discovered_jobs_source_id"),
    )
    op.create_index("ix_discovered_jobs_posted_at", "discovered_jobs", ["posted_at"])
    op.create_index("ix_discovered_jobs_company", "discovered_jobs", ["company"])

    op.create_table(
        "job_matches",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("discovered_job_id", sa.Integer(), sa.ForeignKey("discovered_jobs.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("profile_id", sa.Integer(), sa.ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("skill_match", sa.Integer(), nullable=False),
        sa.Column("seniority_match", sa.Integer(), nullable=False),
        sa.Column("location_match", sa.Integer(), nullable=False),
        sa.Column("remote_match", sa.Integer(), nullable=False),
        sa.Column("salary_match", sa.Integer(), nullable=False),
        sa.Column("freshness", sa.Integer(), nullable=False),
        sa.Column("missing_skills", sa.ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint(
            "user_id", "discovered_job_id", "profile_id",
            name="uq_job_matches_user_job_profile",
        ),
    )

    op.create_table(
        "job_sync_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source", sa.String(32), nullable=False, index=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("job_sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="running"),
        sa.Column("discovered_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inserted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("ix_job_sync_runs_started_at", "job_sync_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_job_sync_runs_started_at", table_name="job_sync_runs")
    op.drop_table("job_sync_runs")
    op.drop_table("job_matches")
    op.drop_index("ix_discovered_jobs_company", table_name="discovered_jobs")
    op.drop_index("ix_discovered_jobs_posted_at", table_name="discovered_jobs")
    op.drop_table("discovered_jobs")
    op.drop_table("job_sources")
