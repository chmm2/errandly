"""users.photo_url (profile avatar)

Revision ID: 0007_user_photo
Revises: 0006_email_verification
Create Date: 2026-07-15

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_user_photo"
down_revision: str | None = "0006_email_verification"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("photo_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "photo_url")
