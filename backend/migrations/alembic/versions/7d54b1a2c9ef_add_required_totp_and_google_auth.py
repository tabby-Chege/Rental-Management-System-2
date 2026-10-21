"""add required TOTP and Google auth fields

Revision ID: 7d54b1a2c9ef
Revises: ae12bc3456de
Create Date: 2026-10-21

"""
from alembic import op
import sqlalchemy as sa


revision = "7d54b1a2c9ef"
down_revision = "ae12bc3456de"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.alter_column(
            "password_hash",
            existing_type=sa.String(length=255),
            nullable=True,
        )
        batch_op.add_column(sa.Column("google_sub", sa.String(length=255)))
        batch_op.add_column(sa.Column("totp_secret", sa.Text()))
        batch_op.add_column(sa.Column("totp_pending_secret", sa.Text()))
        batch_op.add_column(
            sa.Column(
                "totp_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )
        batch_op.add_column(sa.Column("totp_last_counter", sa.Integer()))
        batch_op.create_unique_constraint("uq_users_google_sub", ["google_sub"])


def downgrade():
    op.execute("UPDATE users SET password_hash = '' WHERE password_hash IS NULL")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("uq_users_google_sub", type_="unique")
        batch_op.drop_column("totp_last_counter")
        batch_op.drop_column("totp_enabled")
        batch_op.drop_column("totp_pending_secret")
        batch_op.drop_column("totp_secret")
        batch_op.drop_column("google_sub")
        batch_op.alter_column(
            "password_hash",
            existing_type=sa.String(length=255),
            nullable=False,
        )
