"""errand items: per-item availability + notes, priceless shopping-list lines

Revision ID: 0009_errand_item_availability
Revises: 0008_errand_deadline
Create Date: 2026-07-19

Makes every list-type errand's items addressable so a runner can mark one
"out of stock" and still deliver the rest. Shopping-list items (grocery /
stationery / pharmacy) now live as structured rows too, with no price.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_errand_item_availability"
down_revision: str | None = "0008_errand_deadline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "errand_items",
        sa.Column("is_available", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "errand_items",
        sa.Column("note", sa.String(200), nullable=True),
    )
    # Shopping-list lines carry no price — make the snapshot optional.
    op.alter_column("errand_items", "unit_price_snapshot", nullable=True)


def downgrade() -> None:
    op.alter_column("errand_items", "unit_price_snapshot", nullable=False)
    op.drop_column("errand_items", "note")
    op.drop_column("errand_items", "is_available")
