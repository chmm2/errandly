"""outbox + processed_events, notifications, daily_stats, timetable_slots

Revision ID: 0004_outbox_timetable
Revises: 0003_runners_handoff
Create Date: 2026-07-11

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004_outbox_timetable"
down_revision: str | None = "0003_runners_handoff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- transactional outbox ---
    op.create_table(
        "outbox_events",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("aggregate_type", sa.String(32), nullable=False),
        sa.Column("aggregate_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Partial index: the relay only ever asks for unpublished rows.
    op.create_index(
        "ix_outbox_unpublished",
        "outbox_events",
        ["created_at"],
        postgresql_where=sa.text("published_at IS NULL"),
    )

    # --- consumer dedupe (at-least-once + idempotency = effectively-once) ---
    op.create_table(
        "processed_events",
        sa.Column("consumer", sa.String(64), primary_key=True),
        sa.Column("event_id", sa.UUID(), primary_key=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    # --- notifications (written by the notification consumer) ---
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(32), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("data", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_notifications_user_created", "notifications", ["user_id", "created_at"])

    # --- analytics read model (upserted by the analytics consumer) ---
    op.create_table(
        "daily_stats",
        sa.Column("campus_id", sa.UUID(), sa.ForeignKey("campuses.id"), primary_key=True),
        sa.Column("stat_date", sa.Date(), primary_key=True),
        sa.Column("orders_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("orders_completed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("orders_cancelled", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reward_total", sa.Numeric(12, 2), server_default="0", nullable=False),
    )

    # --- timetable (the signature feature) ---
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
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
        sa.CheckConstraint(
            "start_minute >= 0 AND end_minute <= 1440 AND end_minute > start_minute",
            name="ck_timetable_range",
        ),
    )
    op.create_index("ix_timetable_slots_user_id", "timetable_slots", ["user_id"])
    # DB-enforced overlap exclusion: two overlapping slots for the same
    # user+day cannot both commit, however racy the requests are.
    op.execute(
        "ALTER TABLE timetable_slots ADD CONSTRAINT ex_timetable_no_overlap "
        "EXCLUDE USING gist (user_id WITH =, day_of_week WITH =, "
        "int4range(start_minute, end_minute) WITH &&)"
    )


def downgrade() -> None:
    op.drop_table("timetable_slots")
    op.drop_table("daily_stats")
    op.drop_index("ix_notifications_user_created", table_name="notifications")
    op.drop_table("notifications")
    op.drop_table("processed_events")
    op.drop_index("ix_outbox_unpublished", table_name="outbox_events")
    op.drop_table("outbox_events")
