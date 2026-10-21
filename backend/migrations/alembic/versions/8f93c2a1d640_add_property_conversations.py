"""add property conversations and messages

Revision ID: 8f93c2a1d640
Revises: 7d54b1a2c9ef
Create Date: 2026-10-21

"""
from alembic import op
import sqlalchemy as sa


revision = "8f93c2a1d640"
down_revision = "7d54b1a2c9ef"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "property_conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("property_id", sa.Integer(), nullable=False),
        sa.Column("tenant_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"]),
        sa.ForeignKeyConstraint(["tenant_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "property_id",
            "tenant_user_id",
            name="uq_property_conversation_tenant",
        ),
    )
    op.create_index(
        op.f("ix_property_conversations_property_id"),
        "property_conversations",
        ["property_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_property_conversations_tenant_user_id"),
        "property_conversations",
        ["tenant_user_id"],
        unique=False,
    )
    op.create_table(
        "property_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("sender_user_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.String(length=5000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["property_conversations.id"]
        ),
        sa.ForeignKeyConstraint(["sender_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_property_messages_conversation_id"),
        "property_messages",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_property_messages_sender_user_id"),
        "property_messages",
        ["sender_user_id"],
        unique=False,
    )


def downgrade():
    op.drop_index(op.f("ix_property_messages_sender_user_id"), table_name="property_messages")
    op.drop_index(op.f("ix_property_messages_conversation_id"), table_name="property_messages")
    op.drop_table("property_messages")
    op.drop_index(op.f("ix_property_conversations_tenant_user_id"), table_name="property_conversations")
    op.drop_index(op.f("ix_property_conversations_property_id"), table_name="property_conversations")
    op.drop_table("property_conversations")
