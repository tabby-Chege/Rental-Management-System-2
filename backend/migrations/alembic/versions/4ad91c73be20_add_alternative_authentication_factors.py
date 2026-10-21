"""add alternative authentication factors

Revision ID: 4ad91c73be20
Revises: 0b4d9a7f2e61
Create Date: 2026-10-21

"""
from alembic import op
import sqlalchemy as sa


revision = "4ad91c73be20"
down_revision = "0b4d9a7f2e61"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("mfa_phone", sa.String(length=20), nullable=True))
        batch_op.add_column(
            sa.Column(
                "mfa_phone_verified",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
    op.create_table(
        "auth_otp_challenges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("challenge_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("method", sa.String(length=12), nullable=False),
        sa.Column("target", sa.String(length=255), nullable=True),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("challenge_hash"),
    )
    for column in ("challenge_hash", "user_id", "expires_at"):
        op.create_index(
            op.f(f"ix_auth_otp_challenges_{column}"),
            "auth_otp_challenges",
            [column],
            unique=False,
        )
    op.create_table(
        "auth_passkey_challenges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("challenge_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("challenge", sa.String(length=256), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("challenge_hash"),
    )
    for column in ("challenge_hash", "user_id", "expires_at"):
        op.create_index(
            op.f(f"ix_auth_passkey_challenges_{column}"),
            "auth_passkey_challenges",
            [column],
            unique=False,
        )
    op.create_table(
        "passkey_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("credential_id", sa.String(length=1024), nullable=False),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("sign_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credential_id"),
    )
    op.create_index(
        op.f("ix_passkey_credentials_user_id"),
        "passkey_credentials",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "recovery_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "code_hash", name="uq_recovery_code_user_hash"),
    )
    op.create_index(
        op.f("ix_recovery_codes_user_id"), "recovery_codes", ["user_id"], unique=False
    )


def downgrade():
    op.drop_index(op.f("ix_recovery_codes_user_id"), table_name="recovery_codes")
    op.drop_table("recovery_codes")
    op.drop_index(op.f("ix_passkey_credentials_user_id"), table_name="passkey_credentials")
    op.drop_table("passkey_credentials")
    for column in ("expires_at", "user_id", "challenge_hash"):
        op.drop_index(
            op.f(f"ix_auth_passkey_challenges_{column}"),
            table_name="auth_passkey_challenges",
        )
    op.drop_table("auth_passkey_challenges")
    for column in ("expires_at", "user_id", "challenge_hash"):
        op.drop_index(
            op.f(f"ix_auth_otp_challenges_{column}"),
            table_name="auth_otp_challenges",
        )
    op.drop_table("auth_otp_challenges")
    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("mfa_phone_verified")
        batch_op.drop_column("mfa_phone")
