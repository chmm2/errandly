"""Provenance-weighted reputation for matching

Revision ID: 0017_rating_provenance
Revises: 0016_item_aliases
Create Date: 2026-08-26

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017_rating_provenance"
down_revision: str | None = "0016_item_aliases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Kept separate from reputation_score on purpose. reputation_score stays
    # the plain average a person sees on their own profile; this is the
    # provenance-weighted figure ranking reads. Showing someone a silently
    # discounted number on their profile would be worse than not discounting.
    op.add_column(
        "users",
        sa.Column(
            "effective_reputation", sa.Numeric(4, 2), server_default="3.50", nullable=False
        ),
    )
    # How much of that score rests on independent raters, in [0, 1). A runner
    # carried entirely by their own circle reads as unproven, not as bad.
    op.add_column(
        "users",
        sa.Column(
            "rating_confidence", sa.Numeric(4, 3), server_default="0.000", nullable=False
        ),
    )
    op.create_check_constraint(
        "ck_users_effective_reputation",
        "users",
        "effective_reputation >= 0 AND effective_reputation <= 5",
    )
    op.create_check_constraint(
        "ck_users_rating_confidence",
        "users",
        "rating_confidence >= 0 AND rating_confidence <= 1",
    )
    # Ranking reads this per candidate on the offer path.
    op.create_index("ix_users_effective_reputation", "users", ["effective_reputation"])


def downgrade() -> None:
    op.drop_index("ix_users_effective_reputation", table_name="users")
    op.drop_constraint("ck_users_rating_confidence", "users", type_="check")
    op.drop_constraint("ck_users_effective_reputation", "users", type_="check")
    op.drop_column("users", "rating_confidence")
    op.drop_column("users", "effective_reputation")
