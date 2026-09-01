"""push_tokens — Expo device tokens for OS-level notifications

Revision ID: 0011_push_tokens
Revises: 0010_drop_timetable
Create Date: 2026-08-22

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_push_tokens"
down_revision: str | None = "0010_drop_timetable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "push_tokens",
        # The Expo token is the natural key — the same install always gets the
        # same string back, so re-registering is an upsert, not a duplicate.
        sa.Column("token", sa.String(255), primary_key=True),
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("platform", sa.String(16), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Every send looks tokens up by user.
    op.create_index("ix_push_tokens_user", "push_tokens", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_push_tokens_user", table_name="push_tokens")
    op.drop_table("push_tokens")
