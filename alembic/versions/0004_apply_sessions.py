"""phase 3b: apply_sessions table for browser application agent

Revision ID: 0004_apply_sessions
Revises: 0003_phase2b
Create Date: 2026-06-08 18:30:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_apply_sessions"
down_revision: str | Sequence[str] | None = "0003_phase2b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "apply_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("applications.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("platform", sa.String(16), nullable=False),
        sa.Column("state", sa.String(32), nullable=False, server_default="in_progress"),
        sa.Column("headless", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("job_url", sa.String(2048), nullable=False),
        sa.Column(
            "screenshot_paths",
            sa.ARRAY(sa.String()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ready_for_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extra_json", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_apply_sessions_state", "apply_sessions", ["state"]
    )


def downgrade() -> None:
    op.drop_index("ix_apply_sessions_state", table_name="apply_sessions")
    op.drop_table("apply_sessions")
