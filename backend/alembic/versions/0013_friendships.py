"""friendships

Revision ID: 0013_friendships
Revises: 0012_password_reset_otps
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0013_friendships"
down_revision: str | None = "0012_password_reset_otps"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "friendships",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "user_lo",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_hi",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requested_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("status_before_block", sa.String(16), nullable=True),
        sa.Column(
            "blocked_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_lo", "user_hi", name="uq_friendship_pair"),
        sa.CheckConstraint("user_lo < user_hi", name="ck_friendship_ordered"),
        sa.CheckConstraint(
            "status IN ('PENDING','ACCEPTED','DECLINED','BLOCKED')", name="ck_friendship_status"
        ),
    )
    op.create_index("ix_friendship_lo_status", "friendships", ["user_lo", "status"])
    op.create_index("ix_friendship_hi_status", "friendships", ["user_hi", "status"])


def downgrade() -> None:
    op.drop_index("ix_friendship_hi_status", table_name="friendships")
    op.drop_index("ix_friendship_lo_status", table_name="friendships")
    op.drop_table("friendships")
