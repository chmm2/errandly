"""Escrow headroom — hold more than the estimate so overspend is covered

Revision ID: 0020_escrow_buffer
Revises: 0019_claim_store
Create Date: 2026-08-27

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0020_escrow_buffer"
down_revision: str | None = "0019_claim_store"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Recorded per hold rather than derived from the current setting, so a
    # receipt still reconciles after the percentage is retuned. An errand held
    # under a 15% buffer must keep explaining itself as 15% forever.
    op.add_column(
        "escrow_holds",
        sa.Column("buffer", sa.Numeric(12, 2), server_default="0", nullable=False),
    )
    # Existing holds were placed without headroom; 0 is the honest value for
    # them and the server_default already supplies it.


def downgrade() -> None:
    op.drop_column("escrow_holds", "buffer")
