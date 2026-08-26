"""Escrow holds, wallet directions, runner price claims, fraud flags + strikes

Revision ID: 0011_escrow_fraud
Revises: 0010_drop_timetable
Create Date: 2026-08-26

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0011_escrow_fraud"
down_revision: str | None = "0010_drop_timetable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- ledger gains a direction so escrow can debit ---
    # Existing rows are all REWARD/REIMBURSEMENT payouts, i.e. credits, so the
    # server_default backfills them correctly and no data migration is needed.
    op.add_column(
        "ledger_entries",
        sa.Column("direction", sa.String(8), server_default="CREDIT", nullable=False),
    )
    op.add_column("ledger_entries", sa.Column("memo", sa.Text(), nullable=True))

    op.drop_constraint("ck_ledger_type", "ledger_entries", type_="check")
    op.create_check_constraint(
        "ck_ledger_type",
        "ledger_entries",
        "entry_type IN ('TOPUP','HOLD','REFUND','REWARD','REIMBURSEMENT','CLAWBACK')",
    )
    op.create_check_constraint(
        "ck_ledger_direction", "ledger_entries", "direction IN ('CREDIT','DEBIT')"
    )
    op.create_check_constraint(
        "ck_ledger_type_direction",
        "ledger_entries",
        "(entry_type IN ('HOLD','CLAWBACK') AND direction = 'DEBIT') OR "
        "(entry_type IN ('TOPUP','REFUND','REWARD','REIMBURSEMENT') AND direction = 'CREDIT')",
    )
    op.create_index("ix_ledger_errand", "ledger_entries", ["errand_id"])
    # Idempotency gate: a Kafka redelivery collides here instead of paying twice.
    op.create_unique_constraint(
        "uq_ledger_errand_user_type", "ledger_entries", ["errand_id", "user_id", "entry_type"]
    )

    # --- escrow ---
    op.create_table(
        "escrow_holds",
        sa.Column(
            "errand_id",
            sa.UUID(),
            sa.ForeignKey("errands.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("requester_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("items_total", sa.Numeric(12, 2), server_default="0", nullable=False),
        sa.Column("reward", sa.Numeric(12, 2), server_default="0", nullable=False),
        sa.Column("collect_amount", sa.Numeric(12, 2), server_default="0", nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("released_amount", sa.Numeric(12, 2), server_default="0", nullable=False),
        sa.Column("status", sa.String(16), server_default="HELD", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('HELD','RELEASED','REFUNDED','PENDING_REVIEW')", name="ck_escrow_status"
        ),
        sa.CheckConstraint("amount > 0", name="ck_escrow_amount"),
        sa.CheckConstraint("released_amount >= 0", name="ck_escrow_released"),
        # A payout can never exceed its hold - enforced by the database, not
        # only by the service that writes it.
        sa.CheckConstraint("released_amount <= amount", name="ck_escrow_no_overdraw"),
    )
    op.create_index("ix_escrow_holds_requester_id", "escrow_holds", ["requester_id"])
    op.create_index("ix_escrow_status", "escrow_holds", ["status"])

    # --- reference prices ---
    op.create_table(
        "reference_prices",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("campus_id", sa.UUID(), sa.ForeignKey("campuses.id"), nullable=False),
        sa.Column("item_key", sa.String(120), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("reference_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("band_min", sa.Numeric(10, 2), nullable=False),
        sa.Column("band_max", sa.Numeric(10, 2), nullable=False),
        sa.Column("tolerance_pct", sa.Numeric(5, 2), server_default="15.00", nullable=False),
        sa.Column("source", sa.String(8), server_default="ADMIN", nullable=False),
        sa.Column("sample_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_estimated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.UniqueConstraint("campus_id", "item_key", name="uq_reference_campus_item"),
        sa.CheckConstraint("band_min > 0", name="ck_reference_band_min"),
        sa.CheckConstraint("band_max >= band_min", name="ck_reference_band_order"),
        # The estimator may never write a value outside the admin band. This is
        # the constraint that stops fraudulent claims retraining the detector.
        sa.CheckConstraint(
            "reference_price BETWEEN band_min AND band_max", name="ck_reference_in_band"
        ),
        sa.CheckConstraint("source IN ('ADMIN','AUTO')", name="ck_reference_source"),
        sa.CheckConstraint("tolerance_pct >= 0", name="ck_reference_tolerance"),
    )
    op.create_index("ix_reference_campus", "reference_prices", ["campus_id"])

    op.create_table(
        "reference_price_proposals",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "reference_price_id",
            sa.UUID(),
            sa.ForeignKey("reference_prices.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("proposed_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("proposed_band_min", sa.Numeric(10, 2), nullable=False),
        sa.Column("proposed_band_max", sa.Numeric(10, 2), nullable=False),
        sa.Column("observed_median", sa.Numeric(10, 2), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), server_default="PENDING", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint("status IN ('PENDING','APPROVED','REJECTED')", name="ck_proposal_status"),
        sa.CheckConstraint("proposed_price > 0", name="ck_proposal_price"),
    )
    op.create_index(
        "ix_reference_price_proposals_reference_price_id",
        "reference_price_proposals",
        ["reference_price_id"],
    )
    op.create_index("ix_proposal_status", "reference_price_proposals", ["status"])

    # --- runner price claims ---
    op.create_table(
        "runner_price_claims",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column(
            "errand_id",
            sa.UUID(),
            sa.ForeignKey("errands.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("runner_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("campus_id", sa.UUID(), sa.ForeignKey("campuses.id"), nullable=False),
        sa.Column("raw_name", sa.String(120), nullable=False),
        sa.Column("item_key", sa.String(120), nullable=False),
        sa.Column("claimed_unit_price", sa.Numeric(10, 2), nullable=False),
        sa.Column("quantity", sa.Integer(), server_default="1", nullable=False),
        sa.Column("reference_snapshot", sa.Numeric(10, 2), nullable=True),
        sa.Column("delta_pct", sa.Numeric(7, 2), nullable=True),
        sa.Column("verdict", sa.String(16), server_default="OK", nullable=False),
        sa.Column("eligible_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("claimed_unit_price >= 0", name="ck_claim_price"),
        sa.CheckConstraint("quantity >= 1", name="ck_claim_quantity"),
        sa.CheckConstraint("verdict IN ('OK','FLAGGED','NO_REFERENCE')", name="ck_claim_verdict"),
        sa.UniqueConstraint("errand_id", "item_key", name="uq_claim_errand_item"),
    )
    op.create_index("ix_claim_runner_created", "runner_price_claims", ["runner_id", "created_at"])
    op.create_index("ix_claim_item", "runner_price_claims", ["campus_id", "item_key"])

    # --- flags + strikes ---
    op.create_table(
        "fraud_flags",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "errand_id", sa.UUID(), sa.ForeignKey("errands.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "claim_id",
            sa.UUID(),
            sa.ForeignKey("runner_price_claims.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rule", sa.String(48), nullable=False),
        sa.Column("severity", sa.Integer(), server_default="1", nullable=False),
        sa.Column("details", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(16), server_default="OPEN", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint("status IN ('OPEN','UPHELD','DISMISSED')", name="ck_flag_status"),
        sa.CheckConstraint("severity BETWEEN 1 AND 3", name="ck_flag_severity"),
    )
    op.create_index("ix_flag_user_created", "fraud_flags", ["user_id", "created_at"])
    op.create_index("ix_flag_status", "fraud_flags", ["status"])

    op.create_table(
        "user_strikes",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "flag_id",
            sa.UUID(),
            sa.ForeignKey("fraud_flags.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lifted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint("level >= 1", name="ck_strike_level"),
        sa.CheckConstraint(
            "action IN ('WARNING','REPUTATION_PENALTY','RUNNER_SUSPENDED','ACCOUNT_SUSPENDED')",
            name="ck_strike_action",
        ),
    )
    op.create_index("ix_strike_user_created", "user_strikes", ["user_id", "created_at"])

    # --- runner fraud block ---
    op.add_column(
        "runner_profiles",
        sa.Column("fraud_blocked_until", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("runner_profiles", "fraud_blocked_until")
    op.drop_index("ix_strike_user_created", table_name="user_strikes")
    op.drop_table("user_strikes")
    op.drop_index("ix_flag_status", table_name="fraud_flags")
    op.drop_index("ix_flag_user_created", table_name="fraud_flags")
    op.drop_table("fraud_flags")
    op.drop_index("ix_claim_item", table_name="runner_price_claims")
    op.drop_index("ix_claim_runner_created", table_name="runner_price_claims")
    op.drop_table("runner_price_claims")
    op.drop_index("ix_proposal_status", table_name="reference_price_proposals")
    op.drop_index(
        "ix_reference_price_proposals_reference_price_id", table_name="reference_price_proposals"
    )
    op.drop_table("reference_price_proposals")
    op.drop_index("ix_reference_campus", table_name="reference_prices")
    op.drop_table("reference_prices")
    op.drop_index("ix_escrow_status", table_name="escrow_holds")
    op.drop_index("ix_escrow_holds_requester_id", table_name="escrow_holds")
    op.drop_table("escrow_holds")

    op.drop_constraint("uq_ledger_errand_user_type", "ledger_entries", type_="unique")
    op.drop_index("ix_ledger_errand", table_name="ledger_entries")
    op.drop_constraint("ck_ledger_type_direction", "ledger_entries", type_="check")
    op.drop_constraint("ck_ledger_direction", "ledger_entries", type_="check")
    op.drop_constraint("ck_ledger_type", "ledger_entries", type_="check")
    # Anything that is not a legacy payout type cannot survive the rollback.
    op.execute("DELETE FROM ledger_entries WHERE entry_type NOT IN ('REWARD','REIMBURSEMENT')")
    op.create_check_constraint(
        "ck_ledger_type", "ledger_entries", "entry_type IN ('REWARD','REIMBURSEMENT')"
    )
    op.drop_column("ledger_entries", "memo")
    op.drop_column("ledger_entries", "direction")
