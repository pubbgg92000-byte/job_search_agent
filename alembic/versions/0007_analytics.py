"""phase 3e: analytics_snapshots for funnel trend charts

Revision ID: 0007_analytics
Revises: 0006_outreach
Create Date: 2026-06-08 21:30:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_analytics"
down_revision: str | Sequence[str] | None = "0006_outreach"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analytics_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("snapshot_date", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("jobs_discovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("jobs_saved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("applications_created", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("applications_submitted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("messages_sent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recruiter_replies", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("interviews_scheduled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("interviews_completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("offers_received", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("offers_accepted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rejections", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extra_json", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id", "snapshot_date",
            name="uq_analytics_snapshots_user_date",
        ),
    )


def downgrade() -> None:
    op.drop_table("analytics_snapshots")
