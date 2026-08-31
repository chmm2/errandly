"""Record why each runner was offered an errand

Matching ranks candidates by effective distance - distance offset by social
trust, reputation and open-flag penalties - then throws those terms away once
the offer has gone out.

That loss makes a whole class of question unanswerable. Errandly boosts friends
up the offer queue AND reads "friends transacting with each other" as evidence
of a collusion ring, so the router partly manufactures the very signal the
detector treats as evidence. Telling the two apart needs the policy's own
expectation at offer time, which nothing has ever stored.

Analytics only: nothing reads this on a request path, and it is written
best-effort so a logging failure can never stop an errand being offered.

Revision ID: 0020_offer_log
Revises: 0019_claim_store
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0020_offer_log"
down_revision: str | None = "0019_claim_store"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "offer_logs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("errand_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requester_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("campus_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("round_no", sa.Integer(), server_default="1", nullable=False),
        sa.Column("max_hops", sa.SmallInteger(), nullable=True),
        sa.Column("candidates", postgresql.JSONB(), nullable=False),
        sa.Column("accepted_runner_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["errand_id"], ["errands.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requester_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["campus_id"], ["campuses.id"]),
        sa.ForeignKeyConstraint(["accepted_runner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_offer_log_errand", "offer_logs", ["errand_id"])
    op.create_index(
        "ix_offer_log_requester", "offer_logs", ["requester_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_offer_log_requester", table_name="offer_logs")
    op.drop_index("ix_offer_log_errand", table_name="offer_logs")
    op.drop_table("offer_logs")
