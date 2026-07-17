"""email verification: users.email_verified_at + email_otps

Revision ID: 0006_email_verification
Revises: 0005_catalog_rbac_ledger
Create Date: 2026-07-14

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006_email_verification"
down_revision: str | None = "0005_catalog_rbac_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "email_otps",
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("code_hash", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    # Existing accounts predate verification — treat them as already verified
    # so nobody gets locked out by the new gate.
    op.execute("UPDATE users SET email_verified_at = now() WHERE account_status = 'ACTIVE'")


def downgrade() -> None:
    op.drop_table("email_otps")
    op.drop_column("users", "email_verified_at")
