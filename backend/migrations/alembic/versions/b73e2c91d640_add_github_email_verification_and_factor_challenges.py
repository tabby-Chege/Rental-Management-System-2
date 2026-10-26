"""add GitHub identity, email verification and single-use factor challenges

Revision ID: b73e2c91d640
Revises: 9c82f4b6a103
Create Date: 2026-10-26
"""

from alembic import op
import sqlalchemy as sa


revision = "b73e2c91d640"
down_revision = "9c82f4b6a103"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(
            sa.Column("github_sub", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.create_unique_constraint(
            "uq_users_github_sub", ["github_sub"]
        )

    op.create_table(
        "auth_factor_challenges",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("challenge_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("challenge_hash"),
    )

    op.create_index(
        "ix_auth_factor_challenges_challenge_hash",
        "auth_factor_challenges",
        ["challenge_hash"],
    )
    op.create_index(
        "ix_auth_factor_challenges_user_id",
        "auth_factor_challenges",
        ["user_id"],
    )
    op.create_index(
        "ix_auth_factor_challenges_expires_at",
        "auth_factor_challenges",
        ["expires_at"],
    )


def downgrade():
    op.drop_index(
        "ix_auth_factor_challenges_expires_at",
        table_name="auth_factor_challenges",
    )
    op.drop_index(
        "ix_auth_factor_challenges_user_id",
        table_name="auth_factor_challenges",
    )
    op.drop_index(
        "ix_auth_factor_challenges_challenge_hash",
        table_name="auth_factor_challenges",
    )
    op.drop_table("auth_factor_challenges")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("uq_users_github_sub", type_="unique")
        batch_op.drop_column("email_verified_at")
        batch_op.drop_column("github_sub")
