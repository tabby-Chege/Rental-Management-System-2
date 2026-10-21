"""Add payment providers, rent schedules, and deposit ledger.

Revision ID: c38f1a20d7b4
Revises: f4e2c9a81d70
Create Date: 2026-10-21
"""

from alembic import op
import sqlalchemy as sa


revision = "c38f1a20d7b4"
down_revision = "f4e2c9a81d70"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("payments") as batch_op:
        batch_op.add_column(
            sa.Column(
                "currency",
                sa.String(length=3),
                nullable=False,
                server_default="KES",
            )
        )
        batch_op.add_column(
            sa.Column(
                "provider",
                sa.String(length=40),
                nullable=False,
                server_default="manual",
            )
        )
        batch_op.add_column(
            sa.Column("provider_reference", sa.String(length=160), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "payment_type",
                sa.String(length=20),
                nullable=False,
                server_default="rent",
            )
        )
        batch_op.create_check_constraint(
            "ck_payments_payment_type",
            "payment_type IN ('reservation', 'rent', 'deposit', 'other')",
        )

    op.execute(
        """
        UPDATE payments
        SET currency = (
            SELECT properties.currency
            FROM leases
            JOIN units ON units.id = leases.unit_id
            JOIN properties ON properties.id = units.property_id
            WHERE leases.id = payments.lease_id
        )
        """
    )
    op.create_index(
        "uq_payments_provider_reference",
        "payments",
        ["provider", "provider_reference"],
        unique=True,
        sqlite_where=sa.text("provider_reference IS NOT NULL"),
        postgresql_where=sa.text("provider_reference IS NOT NULL"),
    )

    op.create_table(
        "payment_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("lease_id", sa.Integer(), nullable=True),
        sa.Column("application_id", sa.Integer(), nullable=True),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_reference", sa.String(length=160), nullable=True),
        sa.Column("amount", sa.Numeric(12, 3), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("payment_type", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("checkout_url", sa.String(length=2048), nullable=True),
        sa.Column("customer_email", sa.String(length=254), nullable=False),
        sa.Column("phone_number", sa.String(length=20), nullable=True),
        sa.Column("lease_end_date", sa.Date(), nullable=True),
        sa.Column("provider_data", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "lease_id IS NOT NULL OR application_id IS NOT NULL",
            name="ck_payment_attempts_target",
        ),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"]),
        sa.ForeignKeyConstraint(["lease_id"], ["leases.id"]),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("idempotency_key", name="uq_payment_attempts_idempotency_key"),
    )
    op.create_index("ix_payment_attempts_user_id", "payment_attempts", ["user_id"])
    op.create_index("ix_payment_attempts_lease_id", "payment_attempts", ["lease_id"])
    op.create_index(
        "ix_payment_attempts_application_id",
        "payment_attempts",
        ["application_id"],
    )
    op.create_index(
        "uq_payment_attempts_provider_reference",
        "payment_attempts",
        ["provider", "provider_reference"],
        unique=True,
        sqlite_where=sa.text("provider_reference IS NOT NULL"),
        postgresql_where=sa.text("provider_reference IS NOT NULL"),
    )

    op.create_table(
        "rent_schedules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lease_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 3), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("due_day", sa.Integer(), nullable=False),
        sa.Column("next_due_date", sa.Date(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("due_day BETWEEN 1 AND 31", name="ck_rent_schedules_due_day"),
        sa.CheckConstraint("amount > 0", name="ck_rent_schedules_amount"),
        sa.ForeignKeyConstraint(["lease_id"], ["leases.id"]),
        sa.UniqueConstraint("lease_id", name="uq_rent_schedules_lease_id"),
    )
    op.create_index(
        "ix_rent_schedules_next_due_date", "rent_schedules", ["next_due_date"]
    )

    op.create_table(
        "rent_invoices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lease_id", sa.Integer(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 3), nullable=False),
        sa.Column("amount_paid", sa.Numeric(12, 3), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_rent_invoices_amount"),
        sa.CheckConstraint("amount_paid >= 0", name="ck_rent_invoices_amount_paid"),
        sa.CheckConstraint(
            "status IN ('open', 'partial', 'paid', 'overdue')",
            name="ck_rent_invoices_status",
        ),
        sa.ForeignKeyConstraint(["lease_id"], ["leases.id"]),
        sa.UniqueConstraint("lease_id", "due_date", name="uq_rent_invoices_lease_due"),
    )
    op.create_index("ix_rent_invoices_lease_id", "rent_invoices", ["lease_id"])
    op.create_index("ix_rent_invoices_due_date", "rent_invoices", ["due_date"])

    op.create_table(
        "payment_allocations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("payment_id", sa.Integer(), nullable=False),
        sa.Column("rent_invoice_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 3), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_payment_allocations_amount"),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.ForeignKeyConstraint(["rent_invoice_id"], ["rent_invoices.id"]),
        sa.UniqueConstraint(
            "payment_id",
            "rent_invoice_id",
            name="uq_payment_allocations_payment_invoice",
        ),
    )

    op.create_table(
        "deposit_ledger_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("lease_id", sa.Integer(), nullable=False),
        sa.Column("payment_id", sa.Integer(), nullable=True),
        sa.Column("entry_type", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(12, 3), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "entry_type IN ('charge', 'payment', 'refund', 'adjustment')",
            name="ck_deposit_ledger_entry_type",
        ),
        sa.CheckConstraint("amount > 0", name="ck_deposit_ledger_amount"),
        sa.ForeignKeyConstraint(["lease_id"], ["leases.id"]),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
    )
    op.create_index(
        "ix_deposit_ledger_entries_lease_id", "deposit_ledger_entries", ["lease_id"]
    )
    op.execute(
        """
        INSERT INTO deposit_ledger_entries
            (lease_id, entry_type, amount, currency, note, created_at)
        SELECT leases.id, 'charge', leases.deposit, properties.currency,
               'Initial lease deposit', CURRENT_TIMESTAMP
        FROM leases
        JOIN units ON units.id = leases.unit_id
        JOIN properties ON properties.id = units.property_id
        WHERE leases.deposit > 0
        """
    )

    op.create_table(
        "email_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_key", sa.String(length=180), nullable=False),
        sa.Column("recipient", sa.String(length=254), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("event_key", name="uq_email_outbox_event_key"),
    )


def downgrade():
    op.drop_table("email_outbox")
    op.drop_index("ix_deposit_ledger_entries_lease_id", table_name="deposit_ledger_entries")
    op.drop_table("deposit_ledger_entries")
    op.drop_table("payment_allocations")
    op.drop_index("ix_rent_invoices_due_date", table_name="rent_invoices")
    op.drop_index("ix_rent_invoices_lease_id", table_name="rent_invoices")
    op.drop_table("rent_invoices")
    op.drop_index("ix_rent_schedules_next_due_date", table_name="rent_schedules")
    op.drop_table("rent_schedules")
    op.drop_index("uq_payment_attempts_provider_reference", table_name="payment_attempts")
    op.drop_index("ix_payment_attempts_application_id", table_name="payment_attempts")
    op.drop_index("ix_payment_attempts_lease_id", table_name="payment_attempts")
    op.drop_index("ix_payment_attempts_user_id", table_name="payment_attempts")
    op.drop_table("payment_attempts")
    op.drop_index("uq_payments_provider_reference", table_name="payments")
    with op.batch_alter_table("payments") as batch_op:
        batch_op.drop_constraint("ck_payments_payment_type", type_="check")
        batch_op.drop_column("payment_type")
        batch_op.drop_column("provider_reference")
        batch_op.drop_column("provider")
        batch_op.drop_column("currency")
