"""drop timetable_slots — the class-schedule feature was removed

Revision ID: 0010_drop_timetable
Revises: 0009_errand_item_availability
Create Date: 2026-07-19

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_drop_timetable"
down_revision: str | None = "0009_errand_item_availability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS timetable_slots CASCADE")


def downgrade() -> None:
    # Recreate the table shell (data is not restored).
    op.create_table(
        "timetable_slots",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day_of_week", sa.SmallInteger(), nullable=False),
        sa.Column("start_minute", sa.Integer(), nullable=False),
        sa.Column("end_minute", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("day_of_week BETWEEN 0 AND 6", name="ck_timetable_day"),
        sa.CheckConstraint("start_minute < end_minute", name="ck_timetable_range"),
    )
    op.create_index("ix_timetable_slots_user_id", "timetable_slots", ["user_id"])
