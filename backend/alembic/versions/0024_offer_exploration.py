"""Mark the dispatch rounds that were offered without the social boost

A small fraction of rounds are ranked on distance alone, with no hop ceiling.
Those rounds are the control group: the only observations where who took an
errand was not already decided by who the requester is friends with.

The flag has to be stored rather than inferred. Whether a round explored is a
coin flip taken at dispatch time and is not recoverable from the candidate
terms afterwards - a round where nobody happened to be a friend looks identical
to one where friendship was deliberately ignored, and treating the first as a
control would quietly poison the estimate.

Revision ID: 0024_offer_exploration
Revises: 0023_offer_log
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0024_offer_exploration"
down_revision: str | None = "0023_offer_log"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "offer_logs",
        sa.Column(
            "exploring", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    # Analysis reads the control group on its own, and it is the small side of
    # a very lopsided split.
    op.create_index(
        "ix_offer_log_exploring",
        "offer_logs",
        ["exploring", "created_at"],
        postgresql_where=sa.text("exploring"),
    )


def downgrade() -> None:
    op.drop_index("ix_offer_log_exploring", table_name="offer_logs")
    op.drop_column("offer_logs", "exploring")
