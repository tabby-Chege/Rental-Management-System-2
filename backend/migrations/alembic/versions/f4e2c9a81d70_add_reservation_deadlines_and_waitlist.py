"""Add reservation deadlines, waitlists, and notifications.

Revision ID: f4e2c9a81d70
Revises: fb7d8954b3ce
Create Date: 2026-10-20
"""

from alembic import op
import sqlalchemy as sa


revision = "f4e2c9a81d70"
down_revision = "fb7d8954b3ce"
branch_labels = None
depends_on = None

ACTIVE_RESERVATION_PREDICATE = "status IN ('approved', 'offered', 'paid')"


def upgrade():
    with op.batch_alter_table("properties") as batch_op:
        batch_op.add_column(
            sa.Column(
                "reservation_hold_hours",
                sa.Integer(),
                server_default="48",
                nullable=False,
            )
        )
        batch_op.create_check_constraint(
            "ck_properties_reservation_hold_hours",
            "reservation_hold_hours BETWEEN 1 AND 720",
        )

    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_constraint("ck_applications_status", type_="check")
        batch_op.add_column(sa.Column("lease_end_date", sa.Date(), nullable=True))
        batch_op.add_column(
            sa.Column("payment_due_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(sa.Column("lease_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_applications_lease_id_leases",
            "leases",
            ["lease_id"],
            ["id"],
        )
        batch_op.create_check_constraint(
            "ck_applications_status",
            "status IN ('pending', 'approved', 'declined', 'waitlisted', "
            "'offered', 'expired', 'paid', 'leased')",
        )
        batch_op.create_index(
            "ix_applications_payment_due_at",
            ["payment_due_at"],
            unique=False,
        )

    op.create_index(
        "uq_applications_active_reservation_unit",
        "applications",
        ["unit_id"],
        unique=True,
        sqlite_where=sa.text(ACTIVE_RESERVATION_PREDICATE),
        postgresql_where=sa.text(ACTIVE_RESERVATION_PREDICATE),
    )

    op.create_table(
        "reservation_notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column("notification_type", sa.String(length=32), nullable=False),
        sa.Column("event_key", sa.String(length=180), nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "event_key", name="uq_reservation_notifications_event"
        ),
    )
    op.create_index(
        "ix_reservation_notifications_user_created",
        "reservation_notifications",
        ["user_id", "created_at"],
        unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_reservation_notifications_user_created",
        table_name="reservation_notifications",
    )
    op.drop_table("reservation_notifications")
    op.drop_index(
        "uq_applications_active_reservation_unit",
        table_name="applications",
    )
    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_index("ix_applications_payment_due_at")
        batch_op.drop_constraint("ck_applications_status", type_="check")
        batch_op.drop_constraint(
            "fk_applications_lease_id_leases", type_="foreignkey"
        )
        batch_op.drop_column("lease_id")
        batch_op.drop_column("payment_due_at")
        batch_op.drop_column("lease_end_date")
        batch_op.create_check_constraint(
            "ck_applications_status",
            "status IN ('pending', 'approved', 'declined')",
        )
    with op.batch_alter_table("properties") as batch_op:
        batch_op.drop_constraint(
            "ck_properties_reservation_hold_hours", type_="check"
        )
        batch_op.drop_column("reservation_hold_hours")
