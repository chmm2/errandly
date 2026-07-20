"""Escrow holds + tamper-evident hash-chained ledger

Revision ID: 0010_escrow_hash_ledger
Revises: 0009_errand_item_availability
Create Date: 2026-07-20

Turns the append-only ledger into a per-campus HMAC hash chain (signed
double-entry amounts, prev_hash/entry_hash links) and adds escrow_holds, the
per-errand record of funds held from the customer while an order is in flight.

Note: ledger_entries.account_id drops its FK to users — it now also holds
system-account sentinels (ESCROW / PLATFORM) that are not rows in users.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0010_escrow_hash_ledger"
down_revision: str | None = "0009_errand_item_availability"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- reshape ledger_entries into the hash chain ---
    op.drop_constraint("ck_ledger_type", "ledger_entries", type_="check")
    op.drop_constraint("ck_ledger_amount", "ledger_entries", type_="check")
    op.drop_constraint("ledger_entries_user_id_fkey", "ledger_entries", type_="foreignkey")
    op.drop_index("ix_ledger_user_created", table_name="ledger_entries")
    op.alter_column("ledger_entries", "user_id", new_column_name="account_id")
    op.alter_column("ledger_entries", "entry_type", type_=sa.String(20))

    op.add_column("ledger_entries", sa.Column("campus_id", sa.UUID(), nullable=True))
    op.add_column("ledger_entries", sa.Column("seq", sa.Integer(), nullable=True))
    op.add_column(
        "ledger_entries",
        sa.Column("prev_hash", sa.LargeBinary(), server_default=sa.text("'\\x'::bytea"), nullable=False),
    )
    op.add_column(
        "ledger_entries",
        sa.Column("entry_hash", sa.LargeBinary(), server_default=sa.text("'\\x'::bytea"), nullable=False),
    )
    # Backfill any pre-existing rows (empty on a fresh install): campus from the
    # linked errand, seq by created order within a campus.
    op.execute(
        "UPDATE ledger_entries le SET campus_id = e.campus_id "
        "FROM errands e WHERE le.errand_id = e.id AND le.campus_id IS NULL"
    )
    op.execute(
        "UPDATE ledger_entries le SET seq = s.rn FROM ("
        "  SELECT id, row_number() OVER (PARTITION BY campus_id ORDER BY created_at) AS rn"
        "  FROM ledger_entries) s WHERE le.id = s.id AND le.seq IS NULL"
    )
    op.alter_column("ledger_entries", "prev_hash", server_default=None)
    op.alter_column("ledger_entries", "entry_hash", server_default=None)
    # created_at is now app-set (part of the hash), so drop the DB default.
    op.alter_column("ledger_entries", "created_at", server_default=None)

    op.create_foreign_key(
        "ledger_entries_campus_id_fkey", "ledger_entries", "campuses", ["campus_id"], ["id"]
    )
    op.create_check_constraint(
        "ck_ledger_type", "ledger_entries",
        "entry_type IN ('TOPUP','HOLD','ESCROW','REWARD','REIMBURSEMENT',"
        "'CONVENIENCE_FEE','REFUND')",
    )
    op.create_check_constraint("ck_ledger_amount", "ledger_entries", "amount <> 0")
    op.create_unique_constraint(
        "uq_ledger_campus_seq", "ledger_entries", ["campus_id", "seq"]
    )
    op.create_index("ix_ledger_account_created", "ledger_entries", ["account_id", "created_at"])
    op.create_index("ix_ledger_campus_seq", "ledger_entries", ["campus_id", "seq"])

    # --- escrow_holds ---
    op.create_table(
        "escrow_holds",
        sa.Column("errand_id", sa.UUID(), sa.ForeignKey("errands.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("campus_id", sa.UUID(), sa.ForeignKey("campuses.id"), nullable=False),
        sa.Column("requester_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("runner_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("item_total", sa.Numeric(12, 2), nullable=False),
        sa.Column("runner_fee", sa.Numeric(12, 2), nullable=False),
        sa.Column("convenience_fee", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(16), server_default="HELD", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("held_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('HELD','RELEASED','REFUNDED')", name="ck_escrow_status"),
        sa.CheckConstraint("total_amount >= 0", name="ck_escrow_total"),
    )


def downgrade() -> None:
    op.drop_table("escrow_holds")

    op.drop_index("ix_ledger_campus_seq", table_name="ledger_entries")
    op.drop_index("ix_ledger_account_created", table_name="ledger_entries")
    op.drop_constraint("uq_ledger_campus_seq", "ledger_entries", type_="unique")
    op.drop_constraint("ck_ledger_amount", "ledger_entries", type_="check")
    op.drop_constraint("ck_ledger_type", "ledger_entries", type_="check")
    op.drop_constraint("ledger_entries_campus_id_fkey", "ledger_entries", type_="foreignkey")
    op.drop_column("ledger_entries", "entry_hash")
    op.drop_column("ledger_entries", "prev_hash")
    op.drop_column("ledger_entries", "seq")
    op.drop_column("ledger_entries", "campus_id")
    op.alter_column("ledger_entries", "entry_type", type_=sa.String(16))
    op.alter_column("ledger_entries", "account_id", new_column_name="user_id")
    op.alter_column(
        "ledger_entries", "created_at", server_default=sa.text("now()")
    )
    op.create_foreign_key(
        "ledger_entries_user_id_fkey", "ledger_entries", "users", ["user_id"], ["id"]
    )
    op.create_index("ix_ledger_user_created", "ledger_entries", ["user_id", "created_at"])
    op.create_check_constraint(
        "ck_ledger_type", "ledger_entries", "entry_type IN ('REWARD','REIMBURSEMENT')"
    )
    op.create_check_constraint("ck_ledger_amount", "ledger_entries", "amount > 0")
