"""Percentage-scaled price allowance

A flat rupee tolerance could not work across a canteen menu: 20 rupees is +80%
on a 25-rupee puff and +4% on a 500-rupee grocery run. Measured before this
change, a 10-rupee masala tea claimed at 29 - a 190% inflation, three units on
one errand - was paid in full because 19 sits under a flat 20 line.

The allowance is now a share of the item's own reference price, floored so
cheap items keep a usable margin and capped by tolerance_abs, whose meaning
becomes "the most the allowance may ever be" rather than "the allowance".
Expensive items are therefore unaffected.

Revision ID: 0018_scaled_tolerance
Revises: 0017_rating_provenance
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0018_scaled_tolerance"
down_revision: str | None = "0017_rating_provenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reference_prices",
        sa.Column(
            "tolerance_pct",
            sa.Numeric(4, 3),
            nullable=False,
            server_default="0.400",
        ),
    )
    op.create_check_constraint(
        "ck_reference_tolerance_pct",
        "reference_prices",
        "tolerance_pct >= 0 AND tolerance_pct <= 1",
    )


def downgrade() -> None:
    op.drop_constraint("ck_reference_tolerance_pct", "reference_prices", type_="check")
    op.drop_column("reference_prices", "tolerance_pct")
