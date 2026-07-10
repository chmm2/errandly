"""runner profiles, fulfilment types, verified-handoff fields + encrypted OTPs

Revision ID: 0003_runners_handoff
Revises: 0002_errands
Create Date: 2026-07-10

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_runners_handoff"
down_revision: str | None = "0002_errands"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runner_profiles",
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("campus_id", sa.UUID(), sa.ForeignKey("campuses.id"), nullable=False),
        sa.Column("is_available", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("max_load", sa.Integer(), server_default="2", nullable=False),
        sa.Column("last_lat", sa.Numeric(9, 6), nullable=True),
        sa.Column("last_lng", sa.Numeric(9, 6), nullable=True),
        sa.Column("location_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )

    op.add_column(
        "errands",
        sa.Column("fulfillment_type", sa.String(16), server_default="CATALOG", nullable=False),
    )
    op.add_column("errands", sa.Column("external_ref", sa.String(100), nullable=True))
    op.add_column(
        "errands",
        sa.Column("collect_amount", sa.Numeric(12, 2), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        "ck_errands_fulfillment_type",
        "errands",
        "fulfillment_type IN ('CATALOG','GATE_PICKUP','PARCEL_POINT')",
    )
    op.create_check_constraint("ck_errands_collect_amount", "errands", "collect_amount >= 0")
    # Existing rows: derive fulfilment from category.
    op.execute(
        "UPDATE errands SET fulfillment_type = CASE category "
        "WHEN 'CUSTOM' THEN 'GATE_PICKUP' WHEN 'PARCEL' THEN 'PARCEL_POINT' "
        "ELSE 'CATALOG' END"
    )

    op.create_table(
        "errand_handoff_secrets",
        sa.Column(
            "errand_id",
            sa.UUID(),
            sa.ForeignKey("errands.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("otp_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("errand_handoff_secrets")
    op.drop_constraint("ck_errands_collect_amount", "errands")
    op.drop_constraint("ck_errands_fulfillment_type", "errands")
    op.drop_column("errands", "collect_amount")
    op.drop_column("errands", "external_ref")
    op.drop_column("errands", "fulfillment_type")
    op.drop_table("runner_profiles")
