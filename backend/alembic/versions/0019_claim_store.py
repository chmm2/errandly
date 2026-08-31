"""Record which store a price claim came from

Prices genuinely differ between outlets: the same puff is 23 at one canteen and
30 at another. With a single campus reference the median lands between them,
which is wrong in both directions at once - an honest runner buying at the
dearer shop reads as persistently elevated, while a runner inflating at the
cheaper one reads as normal and is better camouflaged than the honest one.

Storing the store lets the reference be adjusted toward what that outlet
actually charges, shrunk by how much evidence exists for it.

Revision ID: 0019_claim_store
Revises: 0018_scaled_tolerance
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0019_claim_store"
down_revision: str | None = "0018_scaled_tolerance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runner_price_claims", sa.Column("store_key", sa.String(120), nullable=True)
    )
    op.create_index(
        "ix_claim_store_item",
        "runner_price_claims",
        ["campus_id", "store_key", "item_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_claim_store_item", table_name="runner_price_claims")
    op.drop_column("runner_price_claims", "store_key")
