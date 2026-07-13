"""RBAC roles, vendors + menus, errand items, ledger, ratings

Revision ID: 0005_catalog_rbac_ledger
Revises: 0004_outbox_timetable
Create Date: 2026-07-12

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005_catalog_rbac_ledger"
down_revision: str | None = "0004_outbox_timetable"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- RBAC ---
    op.add_column("users", sa.Column("role", sa.String(16), server_default="STUDENT", nullable=False))
    op.create_check_constraint("ck_users_role", "users", "role IN ('STUDENT','VENDOR','ADMIN')")
    op.alter_column("users", "student_id", nullable=True)
    op.create_check_constraint(
        "ck_users_student_id_required", "users", "role <> 'STUDENT' OR student_id IS NOT NULL"
    )

    # --- vendors + menus ---
    op.create_table(
        "vendors",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("campus_id", sa.UUID(), sa.ForeignKey("campuses.id"), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("description", sa.String(300), nullable=True),
        sa.Column("is_open", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "category IN ('FOOD','GROCERY','STATIONERY','PHARMACY')", name="ck_vendors_category"
        ),
    )
    op.create_table(
        "menu_items",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("vendor_id", sa.UUID(), sa.ForeignKey("vendors.id", ondelete="CASCADE"), nullable=False),
        sa.Column("section", sa.String(80), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("is_available", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("price >= 0", name="ck_menu_items_price"),
    )
    op.create_index("ix_menu_items_vendor_id", "menu_items", ["vendor_id"])

    # --- errand order lines (price snapshots) + vendor link ---
    op.add_column("errands", sa.Column("vendor_id", sa.UUID(), sa.ForeignKey("vendors.id"), nullable=True))
    op.create_table(
        "errand_items",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("errand_id", sa.UUID(), sa.ForeignKey("errands.id", ondelete="CASCADE"), nullable=False),
        sa.Column("menu_item_id", sa.UUID(), sa.ForeignKey("menu_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name_snapshot", sa.String(120), nullable=False),
        sa.Column("unit_price_snapshot", sa.Numeric(10, 2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.CheckConstraint("quantity >= 1", name="ck_errand_items_quantity"),
    )
    op.create_index("ix_errand_items_errand_id", "errand_items", ["errand_id"])

    # --- append-only ledger ---
    op.create_table(
        "ledger_entries",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("errand_id", sa.UUID(), sa.ForeignKey("errands.id"), nullable=True),
        sa.Column("entry_type", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("entry_type IN ('REWARD','REIMBURSEMENT')", name="ck_ledger_type"),
        sa.CheckConstraint("amount > 0", name="ck_ledger_amount"),
    )
    op.create_index("ix_ledger_user_created", "ledger_entries", ["user_id", "created_at"])

    # --- ratings ---
    op.create_table(
        "ratings",
        sa.Column("errand_id", sa.UUID(), sa.ForeignKey("errands.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("rater_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ratee_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("stars", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("stars BETWEEN 1 AND 5", name="ck_ratings_stars"),
    )
    op.create_index("ix_ratings_ratee_id", "ratings", ["ratee_id"])


def downgrade() -> None:
    op.drop_table("ratings")
    op.drop_index("ix_ledger_user_created", table_name="ledger_entries")
    op.drop_table("ledger_entries")
    op.drop_index("ix_errand_items_errand_id", table_name="errand_items")
    op.drop_table("errand_items")
    op.drop_column("errands", "vendor_id")
    op.drop_index("ix_menu_items_vendor_id", table_name="menu_items")
    op.drop_table("menu_items")
    op.drop_table("vendors")
    op.drop_constraint("ck_users_student_id_required", "users")
    op.alter_column("users", "student_id", nullable=False)
    op.drop_constraint("ck_users_role", "users")
    op.drop_column("users", "role")
