"""Runners declare what they actually paid, at pickup

Revision ID: 0021_amount_spent
Revises: 0020_escrow_buffer
Create Date: 2026-08-31

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0021_amount_spent"
down_revision: str | None = "0020_escrow_buffer"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable with NO default: "never declared" and "declared zero" are
    # different facts and settlement treats them differently. Backfilling
    # existing rows with 0 would assert every past runner spent nothing.
    op.add_column(
        "errands",
        sa.Column("amount_spent", sa.Numeric(12, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("errands", "amount_spent")
