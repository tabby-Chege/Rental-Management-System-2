"""add conversation context and read state

Revision ID: 9c82f4b6a103
Revises: 8f93c2a1d640
Create Date: 2026-10-21

"""
from alembic import op
import sqlalchemy as sa


revision = "9c82f4b6a103"
down_revision = "4ad91c73be20"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("property_conversations") as batch_op:
        batch_op.drop_constraint(
            "uq_property_conversation_tenant", type_="unique"
        )
        batch_op.add_column(sa.Column("unit_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("application_id", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "context_key",
                sa.String(length=64),
                nullable=False,
                server_default="property",
            )
        )
        batch_op.add_column(sa.Column("tenant_read_at", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("landlord_read_at", sa.DateTime(timezone=True)))
        batch_op.create_foreign_key(
            "fk_property_conversations_unit_id_units",
            "units",
            ["unit_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_property_conversations_application_id_applications",
            "applications",
            ["application_id"],
            ["id"],
        )
        batch_op.create_unique_constraint(
            "uq_property_conversation_context",
            ["property_id", "tenant_user_id", "context_key"],
        )
    op.create_index(
        "ix_property_conversations_unit_id",
        "property_conversations",
        ["unit_id"],
    )
    op.create_index(
        "ix_property_conversations_application_id",
        "property_conversations",
        ["application_id"],
    )


def downgrade():
    op.drop_index(
        "ix_property_conversations_application_id",
        table_name="property_conversations",
    )
    op.drop_index(
        "ix_property_conversations_unit_id",
        table_name="property_conversations",
    )
    with op.batch_alter_table("property_conversations") as batch_op:
        batch_op.drop_constraint(
            "uq_property_conversation_context", type_="unique"
        )
        batch_op.drop_constraint(
            "fk_property_conversations_application_id_applications",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_property_conversations_unit_id_units",
            type_="foreignkey",
        )
        batch_op.drop_column("landlord_read_at")
        batch_op.drop_column("tenant_read_at")
        batch_op.drop_column("application_id")
        batch_op.drop_column("unit_id")
        batch_op.drop_column("context_key")
        batch_op.create_unique_constraint(
            "uq_property_conversation_tenant",
            ["property_id", "tenant_user_id"],
        )
