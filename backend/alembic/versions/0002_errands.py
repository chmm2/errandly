"""errands + errand_events (state machine, event-sourced audit, PostGIS drop point)

Revision ID: 0002_errands
Revises: 0001_init
Create Date: 2026-07-10

"""
from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa

from alembic import op

revision: str = "0002_errands"
down_revision: str | None = "0001_init"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "errands",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True
        ),
        sa.Column("campus_id", sa.UUID(), sa.ForeignKey("campuses.id"), nullable=False),
        sa.Column("requester_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("runner_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("pickup_label", sa.String(200), nullable=False),
        sa.Column(
            "drop_point",
            geoalchemy2.Geography(geometry_type="POINT", srid=4326, spatial_index=False),
            nullable=False,
        ),
        sa.Column("drop_lat", sa.Numeric(9, 6), nullable=False),
        sa.Column("drop_lng", sa.Numeric(9, 6), nullable=False),
        sa.Column("drop_label", sa.String(200), nullable=True),
        sa.Column("reward", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(16), server_default="OPEN", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "category IN ('FOOD','GROCERY','PARCEL','STATIONERY','PHARMACY','CUSTOM')",
            name="ck_errands_category",
        ),
        sa.CheckConstraint(
            "status IN ('OPEN','ACCEPTED','IN_PROGRESS','DELIVERED','COMPLETED',"
            "'CANCELLED','EXPIRED')",
            name="ck_errands_status",
        ),
        sa.CheckConstraint("reward >= 0", name="ck_errands_reward"),
    )
    op.create_index("ix_errands_requester_id", "errands", ["requester_id"])
    op.create_index("ix_errands_runner_id", "errands", ["runner_id"])
    op.create_index("ix_errands_campus_status", "errands", ["campus_id", "status"])
    # spatial_index=False on the column: create the GIST index explicitly so
    # it is named and visible in migrations rather than implicit DDL magic.
    op.create_index(
        "ix_errands_drop_point", "errands", ["drop_point"], postgresql_using="gist"
    )

    op.create_table(
        "errand_events",
        sa.Column(
            "id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True
        ),
        sa.Column(
            "errand_id",
            sa.UUID(),
            sa.ForeignKey("errands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_errand_events_errand_id", "errand_events", ["errand_id"])


def downgrade() -> None:
    op.drop_index("ix_errand_events_errand_id", table_name="errand_events")
    op.drop_table("errand_events")
    op.drop_index("ix_errands_drop_point", table_name="errands")
    op.drop_index("ix_errands_campus_status", table_name="errands")
    op.drop_index("ix_errands_runner_id", table_name="errands")
    op.drop_index("ix_errands_requester_id", table_name="errands")
    op.drop_table("errands")
