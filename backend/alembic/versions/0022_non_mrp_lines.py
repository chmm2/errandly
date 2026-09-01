"""Non-MRP shopping-list lines: reference link, and the headroom base

Revision ID: 0022_non_mrp_lines
Revises: 0021_amount_spent
Create Date: 2026-09-01

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0022_non_mrp_lines"
down_revision: str | None = "0021_amount_spent"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Which line was priced off the admin's non-MRP list. SET NULL rather than
    # CASCADE: retiring a reference price must not delete order history, and
    # the line keeps its own price snapshot regardless.
    op.add_column(
        "errand_items",
        sa.Column("reference_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_errand_items_reference",
        "errand_items",
        "reference_prices",
        ["reference_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_errand_items_reference", "errand_items", ["reference_id"]
    )

    # The slice of the estimate headroom was charged on. Recorded per hold so a
    # receipt still reconciles after the percentage is retuned; existing holds
    # were placed under the old whole-estimate rule and 0 is the honest value
    # for them, since nothing links them to a non-MRP subtotal.
    op.add_column(
        "escrow_holds",
        sa.Column(
            "buffer_base", sa.Numeric(12, 2), server_default="0", nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_column("escrow_holds", "buffer_base")
    op.drop_index("ix_errand_items_reference", table_name="errand_items")
    op.drop_constraint("fk_errand_items_reference", "errand_items", type_="foreignkey")
    op.drop_column("errand_items", "reference_id")
