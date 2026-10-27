"""Item aliases — names that mean an item already priced under another word

Revision ID: 0016_item_aliases
Revises: 0015_absolute_threshold
Create Date: 2026-08-26

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_item_aliases"
down_revision: str | None = "0015_absolute_threshold"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "item_aliases",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("campus_id", sa.UUID(), sa.ForeignKey("campuses.id"), nullable=False),
        sa.Column("alias_key", sa.String(120), nullable=False),
        sa.Column("item_key", sa.String(120), nullable=False),
        sa.Column("sample_raw_name", sa.String(120), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("source", sa.String(8), server_default="MODEL", nullable=False),
        sa.Column("status", sa.String(16), server_default="PENDING", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.UniqueConstraint("campus_id", "alias_key", name="uq_item_alias_key"),
        sa.CheckConstraint(
            "status IN ('PENDING','APPROVED','REJECTED')", name="ck_item_alias_status"
        ),
        sa.CheckConstraint("source IN ('MODEL','ADMIN')", name="ck_item_alias_source"),
        # An alias pointing at itself would make resolve_key loop on its own key.
        sa.CheckConstraint("alias_key <> item_key", name="ck_item_alias_not_self"),
    )
    op.create_index(
        "ix_item_alias_campus_status", "item_aliases", ["campus_id", "status"]
    )


def downgrade() -> None:
    op.drop_index("ix_item_alias_campus_status", table_name="item_aliases")
    op.drop_table("item_aliases")
