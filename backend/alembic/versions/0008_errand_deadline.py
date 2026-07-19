"""errand expiry deadline — poster chooses how long to wait for a runner

Revision ID: 0008_errand_deadline
Revises: 0007_user_photo
Create Date: 2026-07-19

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_errand_deadline"
down_revision: str | None = "0007_user_photo"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "errands",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill existing rows to the old fixed 10-minute find window so the
    # expiry sweep can switch to reading expires_at uniformly.
    op.execute(
        "UPDATE errands SET expires_at = created_at + INTERVAL '10 minutes' "
        "WHERE expires_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("errands", "expires_at")
