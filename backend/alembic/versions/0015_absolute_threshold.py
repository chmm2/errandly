"""Absolute rupee threshold + near-line claim tracking

Replaces the percentage tolerance on reference prices with a flat rupee line,
and records enough on each claim to detect a runner who habitually sits just
under that line without ever crossing it.

Revision ID: 0015_absolute_threshold
Revises: 0014_escrow_fraud
Create Date: 2026-08-26

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0015_absolute_threshold"
down_revision: str | None = "0014_escrow_fraud"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- reference prices: flat rupee line instead of a percentage ---
    op.add_column(
        "reference_prices",
        sa.Column("tolerance_abs", sa.Numeric(10, 2), server_default="20.00", nullable=False),
    )
    op.drop_constraint("ck_reference_tolerance", "reference_prices", type_="check")
    op.drop_column("reference_prices", "tolerance_pct")
    op.create_check_constraint(
        "ck_reference_tolerance", "reference_prices", "tolerance_abs > 0"
    )

    # --- claims: snapshot the line and the overshoot ---
    # Snapshotting the threshold keeps past verdicts stable when an admin later
    # moves the line, and lets the "walking the line" query run as plain
    # arithmetic over claim rows with no join to a live reference.
    op.add_column(
        "runner_price_claims",
        sa.Column("threshold_snapshot", sa.Numeric(10, 2), nullable=True),
    )
    op.add_column(
        "runner_price_claims", sa.Column("delta_abs", sa.Numeric(10, 2), nullable=True)
    )
    # Backfill for rows judged under the old percentage rule, so the new
    # detection has history to work with rather than starting blind.
    op.execute(
        """
        UPDATE runner_price_claims
           SET delta_abs = claimed_unit_price - reference_snapshot
         WHERE reference_snapshot IS NOT NULL
           AND delta_abs IS NULL
        """
    )

    # --- claims: ELEVATED verdict (above reference, under the line) ---
    op.drop_constraint("ck_claim_verdict", "runner_price_claims", type_="check")
    op.create_check_constraint(
        "ck_claim_verdict",
        "runner_price_claims",
        "verdict IN ('OK','ELEVATED','FLAGGED','NO_REFERENCE')",
    )


def downgrade() -> None:
    # ELEVATED has no equivalent under the old rule; it was paid in full, so
    # OK is the honest thing to collapse it to.
    op.execute("UPDATE runner_price_claims SET verdict = 'OK' WHERE verdict = 'ELEVATED'")
    op.drop_constraint("ck_claim_verdict", "runner_price_claims", type_="check")
    op.create_check_constraint(
        "ck_claim_verdict",
        "runner_price_claims",
        "verdict IN ('OK','FLAGGED','NO_REFERENCE')",
    )
    op.drop_column("runner_price_claims", "delta_abs")
    op.drop_column("runner_price_claims", "threshold_snapshot")

    op.drop_constraint("ck_reference_tolerance", "reference_prices", type_="check")
    op.add_column(
        "reference_prices",
        sa.Column("tolerance_pct", sa.Numeric(5, 2), server_default="15.00", nullable=False),
    )
    op.drop_column("reference_prices", "tolerance_abs")
    op.create_check_constraint(
        "ck_reference_tolerance", "reference_prices", "tolerance_pct >= 0"
    )
